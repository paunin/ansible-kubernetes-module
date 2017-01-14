# ansible-kubernetes-module
Module for ansible to setup kubernetes objects

## Instalation

* Make sure file `kube_setup.py` is accessable as [ansible module](http://docs.ansible.com/ansible/dev_guide/developing_modules.html#module-paths)

Alternatively you can put it in `library` directory with your playbook

```
|- playbook.yml
|- library
   |- kube_setup.py
```

## Usage

```yaml
- name: create k8s objects from file
  kube_setup:
    file: "object.yml"
    state: "present" # default = "present" [present|absent]
    strategy: "default" # default = default, means - use the most suitable [create_or_replace|create_or_apply|create_or_nothing]
    kubectl_opts: "--context=live" # default = ""
```
