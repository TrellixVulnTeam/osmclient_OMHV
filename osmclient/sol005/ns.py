# Copyright 2018 Telefonica
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
OSM ns API handling
"""

from osmclient.common import utils
from osmclient.common.exceptions import ClientException
from osmclient.common.exceptions import NotFound
import yaml


class Ns(object):

    def __init__(self, http=None, client=None):
        self._http = http
        self._client = client
        self._apiName = '/nslcm'
        self._apiVersion = '/v1'
        self._apiResource = '/ns_instances_content'
        self._apiBase = '{}{}{}'.format(self._apiName,
                                        self._apiVersion, self._apiResource)

    def list(self, filter=None):
        """Returns a list of NS
        """
        filter_string = ''
        if filter:
            filter_string = '?{}'.format(filter)
        resp = self._http.get_cmd('{}{}'.format(self._apiBase,filter_string))
        if resp:
            return resp
        return list()

    def get(self, name):
        """Returns an NS based on name or id
        """
        if utils.validate_uuid4(name):
            for ns in self.list():
                if name == ns['_id']:
                    return ns
        else:
            for ns in self.list():
                if name == ns['name']:
                    return ns
        raise NotFound("ns {} not found".format(name))

    def get_individual(self, name):
        ns_id = name
        if not utils.validate_uuid4(name):
            for ns in self.list():
                if name == ns['name']:
                    ns_id = ns['_id']
                    break
        resp = self._http.get_cmd('{}/{}'.format(self._apiBase, ns_id))
        #resp = self._http.get_cmd('{}/{}/nsd_content'.format(self._apiBase, ns_id))
        #print yaml.safe_dump(resp)
        if resp:
            return resp
        raise NotFound("ns {} not found".format(name))

    def delete(self, name):
        ns = self.get(name)
        resp = self._http.delete_cmd('{}/{}'.format(self._apiBase,ns['_id']))
        #print 'RESP: '.format(resp)
        if resp is None:
            print 'Deleted'
        else:
            raise ClientException("failed to delete ns {}: {}".format(name, resp))

    def create(self, nsd_name, nsr_name, account, config=None,
               ssh_keys=None, description='default description',
               admin_status='ENABLED'):

        nsd = self._client.nsd.get(nsd_name)
        
        datacenter = self._client.vim.get(account)
        if datacenter is None:
            raise NotFound("cannot find datacenter account {}".format(account))

        ns = {}
        ns['nsdId'] = nsd['_id']
        ns['nsName'] = nsr_name
        ns['nsDescription'] = description
        ns['vimAccountId'] = datacenter['_id']
        #ns['userdata'] = {}
        #ns['userdata']['key1']='value1'
        #ns['userdata']['key2']='value2'
        
        if ssh_keys is not None:
            # ssh_keys is comma separate list
            ssh_keys_format = []
            for key in ssh_keys.split(','):
                ssh_keys_format.append({'key-pair-ref': key})

            ns['ssh-authorized-key'] = ssh_keys_format

        #print yaml.safe_dump(ns)
        try:
            self._apiResource = '/ns_instances_content'
            self._apiBase = '{}{}{}'.format(self._apiName,
                                            self._apiVersion, self._apiResource)
            #print resp
            resp = self._http.post_cmd(endpoint=self._apiBase,
                                       postfields_dict=ns)
            if not resp or 'id' not in resp:
                raise ClientException('unexpected response from server: '.format(
                                      resp))
            else:
                print resp['id']
        except ClientException as exc:
            message="failed to create ns: {} nsd: {}\nerror:\n{}".format(
                    nsr_name,
                    nsd_name,
                    exc.message)
            raise ClientException(message)

