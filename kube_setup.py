#!/usr/bin/python
from ansible.module_utils.basic import *
import subprocess
import yaml
import tempfile

DOCUMENTATION = '''
---
module: kube_setup
short_description: module makes sure your kubernetes cluster has required object
'''

EXAMPLES = '''
- name: create k8s objects from file
  kube_setup:
    file: "object.yml"
    state: "present" # default = "present" [present|absent]
    strategy: "default" # default = default, means - use the most suitable [create_or_replace|create_or_apply|create_or_nothing]
    kubectl_opts: "--context=live" # default = ""
'''

STRATEGY_DEFAULT = 'default'
STRATEGY_CREATE_OR_REPLACE = 'create_or_replace'
STRATEGY_CREATE_OR_APPLY = 'create_or_apply'
STRATEGY_CREATE_OR_NOTHING = 'create_or_nothing'

STRATEGIES = {
    'cluster': STRATEGY_CREATE_OR_NOTHING,
    'componentstatus': STRATEGY_CREATE_OR_NOTHING,
    'configmap': STRATEGY_CREATE_OR_REPLACE,
    'daemonset': STRATEGY_CREATE_OR_APPLY,
    'deployment': STRATEGY_CREATE_OR_REPLACE,
    'endpoint': STRATEGY_CREATE_OR_NOTHING,
    'event': STRATEGY_CREATE_OR_NOTHING,
    'horizontalpodautoscaler': STRATEGY_CREATE_OR_NOTHING,
    'ingress': STRATEGY_CREATE_OR_NOTHING,
    'job': STRATEGY_CREATE_OR_APPLY,
    'limitrange': STRATEGY_CREATE_OR_NOTHING,
    'namespace': STRATEGY_CREATE_OR_APPLY,
    'networkpolicies': STRATEGY_CREATE_OR_NOTHING,
    'node': STRATEGY_CREATE_OR_NOTHING,
    'petset': STRATEGY_CREATE_OR_REPLACE,
    'statefulset': STRATEGY_CREATE_OR_REPLACE,
    'persistentvolumeclaim': STRATEGY_CREATE_OR_NOTHING,
    'persistentvolume': STRATEGY_CREATE_OR_APPLY,
    'pod': STRATEGY_CREATE_OR_NOTHING,
    'podsecuritypolicy': STRATEGY_CREATE_OR_NOTHING,
    'podtemplate': STRATEGY_CREATE_OR_NOTHING,
    'replicaset': STRATEGY_CREATE_OR_NOTHING,
    'replicationcontroller': STRATEGY_CREATE_OR_NOTHING,
    'resourcequota': STRATEGY_CREATE_OR_NOTHING,
    'cronjob': STRATEGY_CREATE_OR_REPLACE,
    'scheduledjob': STRATEGY_CREATE_OR_REPLACE,
    'secret': STRATEGY_CREATE_OR_REPLACE,
    'serviceaccount': STRATEGY_CREATE_OR_NOTHING,
    'service': STRATEGY_CREATE_OR_APPLY,
    'storageclass': STRATEGY_CREATE_OR_NOTHING,
    'thirdpartyresource': STRATEGY_CREATE_OR_NOTHING,
}


def kube_objects_present(file_name, strategy):
    """
    Make sure object exists and up to date
    :param strategy: string
    :param file_name: string
    :returns: (error:bool, changed:bool, result:dict)
    """
    changed = False

    docs, error = __get_docs(file_name)

    if error is not None:
        meta = {"status": 'failed', 'file': file_name, 'response': error}
        return True, False, meta

    metas = []
    doc_num = 0
    any_error = False
    any_change = False
    for doc in docs:
        error, k_object_kind, k_object_name, k_object_namespace = __extract_object_info(doc)

        if error is not None:
            meta = {
                "status": 'failed',
                'file': file_name,
                'response': error + '[doc num: ' + str(doc_num) + ']'
            }
            return True, False, meta
        success = False
        current_strategy = STRATEGIES[k_object_kind.lower()] if strategy == STRATEGY_DEFAULT else strategy

        if __object_exist(k_object_kind, k_object_name, k_object_namespace)[0] == True:
            if current_strategy == STRATEGY_CREATE_OR_REPLACE:
                success, output = __replace_object(doc, k_object_namespace)
                changed = success
            elif current_strategy == STRATEGY_CREATE_OR_APPLY:
                success, output = __apply_object(doc, k_object_namespace)
                changed = success
            elif current_strategy == STRATEGY_CREATE_OR_NOTHING:
                success = True
                output = "Nothing to do with object"
        else:
            success, output = __create_object(doc, k_object_namespace)

        if any_error == False and success == False:
            any_error = True

        if any_change == False and changed == True:
            any_change = True

        meta = {
            "status": success,
            'file': file_name,
            'response': output,
            'object_kind': k_object_kind,
            'object_name': k_object_name,
            'object_namespace': k_object_namespace,
            'strategy': current_strategy
        }
        metas.append(meta)
        doc_num = +1

    return any_error, any_change, metas


def kube_objects_absent(file_name):
    """
    Make sure object does not exist in k8s
    :param file_name: str
    :return: (error:bool,changed:bool,metas:dict)
    """
    changed = False

    docs, error = __get_docs(file_name)

    if error is not None:
        meta = {"status": 'failed', 'file': file_name, 'response': error}
        return True, False, meta

    metas = []
    doc_num = 0
    for doc in docs:
        error, k_object_kind, k_object_name, k_object_namespace = __extract_object_info(doc)

        if error is not None:
            meta = {
                "status": 'failed',
                'file': file_name,
                'response': error + '[doc num: ' + str(doc_num) + ']'
            }
            return True, False, meta
        if __object_exist(k_object_kind, k_object_name, k_object_namespace)[0] == True:
            success, output = __delete_object(k_object_kind, k_object_name, k_object_namespace)
            changed = success
        else:
            success = True
            output = "Object already absent"

        meta = {
            "status": success,
            'file': file_name,
            'response': output,
            'object_kind': k_object_kind,
            'object_name': k_object_name,
            'object_namespace': k_object_namespace,
        }
        metas.append(meta)
        doc_num = +1

    return False if meta['status'] else True, changed, metas


def __get_docs(file_name):
    """
    Extract all documents from yaml file
    :param file_name:
    :return: (docs:dict, error:str)
    """
    error = None
    if not os.path.isfile(file_name):
        error = 'File does not exist'
    stream = open(file_name, "r")
    docs = yaml.load_all(stream)
    return docs, error


def __extract_object_info(doc):
    """
    Extract information about object
    :param doc: dict
    :return: (error:str|None, kind:str, name:str, namespace:str|None)
    """
    error = k_object_kind = k_object_name = k_object_namespace = None
    if 'kind' not in doc:
        error = 'No \'kind\' for object'
    else:
        k_object_kind = doc['kind']
        if k_object_kind.lower() not in STRATEGIES:
            error = 'Unsupported object kind ' + k_object_kind
    if 'metadata' not in doc:
        error = 'No \'metadata\' for object'
    else:
        metadata = doc['metadata']
        if 'name' not in metadata:
            error = 'No \'metadata.name\' for object'
        else:
            k_object_name = doc['metadata']['name']

        k_object_namespace = metadata['namespace'] if 'namespace' in metadata else None
    return error, k_object_kind, k_object_name, k_object_namespace


def __object_exist(k_object_kind, k_object_name, k_object_namespace=None):
    """
    Check if object exists

    :param k_object_kind: str
    :param k_object_name: str
    :param k_object_namespace: str|None
    :returns bool, str
    """
    status, result = __kube_exec(
        "get " + k_object_kind + " " + k_object_name + (
            (" --namespace=" + k_object_namespace) if k_object_namespace is not None else ""
        )
    )

    return status, result


def __create_object(doc, namespace=None):
    """
    Create k8s object
    :param doc: dict
    :return bool
    """
    obj_file = __get_object_file(doc)
    return __kube_exec("create -f " + obj_file, namespace)


def __apply_object(doc, namespace=None):
    """
    Apply k8s object
    :param doc: dict
    :return bool
    """
    obj_file = __get_object_file(doc)
    return __kube_exec("apply -f " + obj_file, namespace)


def __replace_object(doc, namespace=None):
    """
    Replace k8s object
    :param doc:
    :return bool
    """
    obj_file = __get_object_file(doc)
    return __kube_exec("replace -f " + obj_file, namespace)


def __delete_object(kind, name, namespace):
    """
    Delete object from kubernetes
    :param kind: str
    :param name: str
    :return:
    """
    return __kube_exec(
        "delete " + kind + " " + name, namespace
    )


def __get_object_file(doc):
    """
    Get name of the file with object
    :param doc:
    :return: str
    """
    obj_file = tempfile.NamedTemporaryFile(delete=False)
    with open(obj_file.name, 'w') as outfile:
        outfile.write(yaml.dump(doc, default_style='"'))
        outfile.close()
    return obj_file.name


def __kube_exec(command, namespace=None):
    """
    Execute k8s command and return status and output
    :param command:
    :return: (status:bool, result:str)
    """
    child = subprocess.Popen(
        "kubectl " + (kubectl_options if kubectl_options else "") + " " +
        ((" --namespace=" + namespace + " ") if namespace is not None else "") +
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output, errors = child.communicate()
    status = True if child.returncode == 0 else False
    result = output if child.returncode == 0 else errors
    return status, result


kubectl_options = ''


def main():
    global kubectl_options

    fields = {
        "file": {"required": True, "type": "str"},
        "kubectl_opts": {"type": "str", "default": ""},
        "state": {
            "default": "present",
            "choices": ['present', 'absent'],
            "type": 'str'
        },
        "strategy": {
            "default": STRATEGY_DEFAULT,
            "choices": [STRATEGY_DEFAULT, STRATEGY_CREATE_OR_REPLACE, STRATEGY_CREATE_OR_APPLY,
                        STRATEGY_CREATE_OR_NOTHING],
            "type": 'str'
        },
    }

    module = AnsibleModule(argument_spec=fields)

    kubectl_options = module.params['kubectl_opts']

    if module.params['state'] == 'present':
        is_error, has_changed, result = kube_objects_present(module.params['file'], module.params['strategy'])
    else:
        is_error, has_changed, result = kube_objects_absent(module.params['file'])

    if not is_error:
        module.exit_json(changed=has_changed, meta=result)
    else:
        module.fail_json(msg="Error creating/updating object[s]", meta=result)


if __name__ == '__main__':
    main()
