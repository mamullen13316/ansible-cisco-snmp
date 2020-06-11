#!/usr/bin/python

# Copyright 2015 Patrick Ogenstad <patrick@ogenstad.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

DOCUMENTATION = '''
---

module: cisco_snmp_switchport
author: Patrick Ogenstad (@networklore)
short_description: Configures switchport settings
description:
    - Configured switchport setting such as port mode and vlans.
requirements:
    - nelsnmp
options:
    host:
        description:
            - Typically set to {{ inventory_hostname }}
        required: true
    version:
        description:
            - SNMP Version to use, 2c or 3
        choices: [ '2c', '3' ]
        required: true
    community:
        description:
            - The SNMP community string, required if version is 2c
        required: false
    level:
        description:
            - Authentication level, required if version is 3
        choices: [ 'authPriv', 'authNoPriv' ]
        required: false
    username:
        description:
            - Username for SNMPv3, required if version is 3
        required: false
    integrity:
        description:
            - Hashing algoritm, required if version is 3
        choices: [ 'md5', 'sha' ]
        required: false
    authkey:
        description:
            - Authentication key, required if version is 3
        required: false
    privacy:
        description:
            - Encryption algoritm, required if level is authPriv
        choices: [ 'des', '3des', 'aes', 'aes192', 'aes256' ]
        required: false
    privkey:
        description:
            - Encryption key, required if version is authPriv
        required: false
    mode:
        description:
            - Mode of the interface
        choices: [ 'access', 'trunk', 'desirable', 'auto', 'trunk-nonegotiate' ]
        required: True
    interface_id:
        description:
            - The SNMP interface id (ifIndex)
        required: false
    interface_name:
        description:
            - The name of the interface
        required: false
    access_vlan:
        description:
            - The access vlan id
        required: false
    native_vlan:
        description:
            - The native vlan id on a trunk port
        required: false

'''

EXAMPLES = '''
# Set interface with id 10001 to access mode in vlan 12
- cisco_snmp_switchport: host={{ inventory_hostname }} version=2c community=private interface_id=10001 mode=access access_vlan=12

# Change FastEthernet0/2 to trunk mode using native vlan 12
- cisco_snmp_switchport:
    host={{ inventory_hostname }}
    version=3
    level=authPriv
    integrity=sha
    privacy=aes
    username=snmp-user
    authkey=abc12345
    privkey=def6789
    mode=trunk
    interface_name="FastEthernet0/2"
    native_vlan=12
'''

from ansible.module_utils.basic import *
from collections import defaultdict

try:
    from nelsnmp.snmp import SnmpHandler
    from nelsnmp.vendors.cisco.oids import CiscoOids
    o = CiscoOids()
    has_nelsnmp = True
except:
    has_nelsnmp = False

NELSNMP_PARAMETERS = (
    'host',
    'community',
    'version',
    'level',
    'integrity',
    'privacy',
    'username',
    'authkey',
    'privkey'
)

PORT_MODE = {
    'trunk': 1,
    'access': 2,
    'desirable': 3,
    'auto': 4,
    'trunk-nonegotiate': 5,
}



def changed_status(changed, has_changed):
    if changed == True:
        has_changed = True
    return has_changed

def set_state(dev, oid, desired_state, module):
    try:
        current_state = dev.get_value(oid)
    except Exception as err:
        module.fail_json(msg=str(err))

    if current_state == desired_state:
        return False
    else:
        try:
            dev.set(oid, desired_state)
        except:
            module.fail_json(msg='Unable to write to device')
        return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            version=dict(required=True, choices=['2c', '3']),
            community=dict(required=False, default=False),
            username=dict(required=False),
            level=dict(required=False, choices=['authNoPriv', 'authPriv']),
            integrity=dict(required=False, choices=['md5', 'sha']),
            privacy=dict(required=False, choices=['des', '3des', 'aes', 'aes192', 'aes256']),
            authkey=dict(required=False),
            privkey=dict(required=False),
            mode=dict(required=True, choices=['access', 'trunk', 'desireable', 'auto', 'trunk-nonegotiate']),
            interface_id=dict(required=False),
            interface_name=dict(required=False),
            access_vlan=dict(required=False),
            native_vlan=dict(required=False),
            removeplaceholder=dict(required=False),
        ),
        mutually_exclusive=(['interface_id', 'interface_name'],),
        required_one_of=(['interface_id', 'interface_name'],),
        required_together=(
            ['username','level','integrity','authkey'],['privacy','privkey'],
        ),
        supports_check_mode=False)

    m_args = module.params

    if not has_nelsnmp:
        module.fail_json(msg='Missing required nelsnmp module (check docs)')

    # Verify that we receive a community when using snmp v2
    if m_args['version'] == "2c":
        if m_args['community'] == False:
            module.fail_json(msg='Community not set when using snmp version 2')

    if m_args['version'] == "3":
        if m_args['username'] == None:
            module.fail_json(msg='Username not set when using snmp version 3')

        if m_args['level'] == "authPriv" and m_args['privacy'] == None:
            module.fail_json(msg='Privacy algorithm not set when using authPriv')

    nelsnmp_args = {}
    for key in m_args:
        if key in NELSNMP_PARAMETERS and m_args[key] != None:
            nelsnmp_args[key] = m_args[key]

    try:
        dev = SnmpHandler(**nelsnmp_args)
    except Exception as err:
        module.fail_json(msg=str(err))

    #return_status = { 'changed': False }
    has_changed = False

    if m_args['interface_name']:
        # Do this through cache in the future
        try:
            interface = False
            vartable = dev.getnext(o.ifDescr)

            for varbinds in vartable:
                for oid, val in varbinds:
                    if m_args['interface_name'] == val:
                        interface = oid.rsplit('.', 1)[-1]

            if interface == False:
                module.fail_json(msg='Unable to find interface')
        except Exception as err:
            module.fail_json(msg=str(err))

    # Check how to get the interface value
    if m_args['interface_id']:
        interface = m_args['interface_id']

    if m_args['mode']:
        oid = o.vlanTrunkPortDynamicState + "." + str(interface)
        desired_state = PORT_MODE[m_args['mode']]
        changed = set_state(dev, oid, desired_state, module)
        has_changed = changed_status(changed, has_changed)

    if m_args['access_vlan']:
        oid = o.vmVlan + "." + str(interface)
        desired_state = int(m_args['access_vlan'])
        changed = set_state(dev, oid, desired_state, module)
        has_changed = changed_status(changed, has_changed)

    if m_args['native_vlan']:
        oid = o.vlanTrunkPortNativeVlan + "." + str(interface)
        desired_state = int(m_args['native_vlan'])
        changed = set_state(dev, oid, desired_state, module)
        has_changed = changed_status(changed, has_changed)

    return_status = { 'changed': has_changed }

    module.exit_json(**return_status)



main()
