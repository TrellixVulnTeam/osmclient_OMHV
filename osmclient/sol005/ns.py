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
from osmclient.common import wait as WaitForStatus
from osmclient.common.exceptions import ClientException
from osmclient.common.exceptions import NotFound
import yaml
import json
import logging


class Ns(object):

    def __init__(self, http=None, client=None):
        self._http = http
        self._client = client
        self._logger = logging.getLogger('osmclient')
        self._apiName = '/nslcm'
        self._apiVersion = '/v1'
        self._apiResource = '/ns_instances_content'
        self._apiBase = '{}{}{}'.format(self._apiName,
                                        self._apiVersion, self._apiResource)

    # NS '--wait' option
    def _wait(self, id, deleteFlag=False):
        self._logger.debug("")
        # Endpoint to get operation status
        apiUrlStatus = '{}{}{}'.format(self._apiName, self._apiVersion, '/ns_lcm_op_occs')
        # Wait for status for NS instance creation/update/deletion
        WaitForStatus.wait_for_status(
            'NS',
            str(id),
            WaitForStatus.TIMEOUT_NS_OPERATION,
            apiUrlStatus,
            self._http.get2_cmd,
            deleteFlag=deleteFlag)

    def list(self, filter=None):
        """Returns a list of NS
        """
        self._logger.debug("")
        self._client.get_token()
        filter_string = ''
        if filter:
            filter_string = '?{}'.format(filter)
        _, resp = self._http.get2_cmd('{}{}'.format(self._apiBase,filter_string))
        if resp:
            return json.loads(resp)
        return list()

    def get(self, name):
        """Returns an NS based on name or id
        """
        self._logger.debug("")
        self._client.get_token()
        if utils.validate_uuid4(name):
            for ns in self.list():
                if name == ns['_id']:
                    return ns
        else:
            for ns in self.list():
                if name == ns['name']:
                    return ns
        raise NotFound("ns '{}' not found".format(name))

    def get_individual(self, name):
        self._logger.debug("")
        self._client.get_token()
        ns_id = name
        if not utils.validate_uuid4(name):
            for ns in self.list():
                if name == ns['name']:
                    ns_id = ns['_id']
                    break
        try:
            _, resp = self._http.get2_cmd('{}/{}'.format(self._apiBase, ns_id))
            #resp = self._http.get_cmd('{}/{}/nsd_content'.format(self._apiBase, ns_id))
            #print(yaml.safe_dump(resp))
            if resp:
                return json.loads(resp)
        except NotFound:
            raise NotFound("ns '{}' not found".format(name))
        raise NotFound("ns '{}' not found".format(name))

    def delete(self, name, force=False, wait=False):
        self._logger.debug("")
        ns = self.get(name)
        querystring = ''
        if force:
            querystring = '?FORCE=True'
        http_code, resp = self._http.delete_cmd('{}/{}{}'.format(self._apiBase,
                                                 ns['_id'], querystring))
        # print('HTTP CODE: {}'.format(http_code))
        # print('RESP: {}'.format(resp))
        if http_code == 202:
            if wait and resp:
                resp = json.loads(resp)
                # For the 'delete' operation, '_id' is used
                self._wait(resp.get('_id'), deleteFlag=True)
            else:
                print('Deletion in progress')
        elif http_code == 204:
            print('Deleted')
        else:
            msg = resp or ""
            # if resp:
            #     try:
            #         msg = json.loads(resp)
            #     except ValueError:
            #         msg = resp
            raise ClientException("failed to delete ns {} - {}".format(name, msg))

    def create(self, nsd_name, nsr_name, account, config=None,
               ssh_keys=None, description='default description',
               admin_status='ENABLED', wait=False):
        self._logger.debug("")
        self._client.get_token()
        nsd = self._client.nsd.get(nsd_name)

        vim_account_id = {}
        wim_account_id = {}

        def get_vim_account_id(vim_account):
            self._logger.debug("")
            if vim_account_id.get(vim_account):
                return vim_account_id[vim_account]
            vim = self._client.vim.get(vim_account)
            if vim is None:
                raise NotFound("cannot find vim account '{}'".format(vim_account))
            vim_account_id[vim_account] = vim['_id']
            return vim['_id']

        def get_wim_account_id(wim_account):
            self._logger.debug("")
            # wim_account can be False (boolean) to indicate not use wim account
            if not isinstance(wim_account, str):
                return wim_account
            if wim_account_id.get(wim_account):
                return wim_account_id[wim_account]
            wim = self._client.wim.get(wim_account)
            if wim is None:
                raise NotFound("cannot find wim account '{}'".format(wim_account))
            wim_account_id[wim_account] = wim['_id']
            return wim['_id']

        ns = {}
        ns['nsdId'] = nsd['_id']
        ns['nsName'] = nsr_name
        ns['nsDescription'] = description
        ns['vimAccountId'] = get_vim_account_id(account)
        #ns['userdata'] = {}
        #ns['userdata']['key1']='value1'
        #ns['userdata']['key2']='value2'

        if ssh_keys is not None:
            ns['ssh_keys'] = []
            for pubkeyfile in ssh_keys.split(','):
                with open(pubkeyfile, 'r') as f:
                    ns['ssh_keys'].append(f.read())
        if config:
            ns_config = yaml.safe_load(config)
            if "vim-network-name" in ns_config:
                ns_config["vld"] = ns_config.pop("vim-network-name")
            if "vld" in ns_config:
                if not isinstance(ns_config["vld"], list):
                    raise ValueError("Error at --config 'vld' must be a list of dictionaries")
                for vld in ns_config["vld"]:
                    if not isinstance(vld, dict):
                        raise ValueError("Error at --config 'vld' must be a list of dictionaries")
                    if vld.get("vim-network-name"):
                        if isinstance(vld["vim-network-name"], dict):
                            vim_network_name_dict = {}
                            for vim_account, vim_net in vld["vim-network-name"].items():
                                vim_network_name_dict[get_vim_account_id(vim_account)] = vim_net
                            vld["vim-network-name"] = vim_network_name_dict
                    if "wim_account" in vld and vld["wim_account"] is not None:
                        vld["wimAccountId"] = get_wim_account_id(vld.pop("wim_account"))
            if "vnf" in ns_config:
                for vnf in ns_config["vnf"]:
                    if vnf.get("vim_account"):
                        vnf["vimAccountId"] = get_vim_account_id(vnf.pop("vim_account"))

            if "additionalParamsForNs" in ns_config:
                if not isinstance(ns_config["additionalParamsForNs"], dict):
                    raise ValueError("Error at --config 'additionalParamsForNs' must be a dictionary")
            if "additionalParamsForVnf" in ns_config:
                if not isinstance(ns_config["additionalParamsForVnf"], list):
                    raise ValueError("Error at --config 'additionalParamsForVnf' must be a list")
                for additional_param_vnf in ns_config["additionalParamsForVnf"]:
                    if not isinstance(additional_param_vnf, dict):
                        raise ValueError("Error at --config 'additionalParamsForVnf' items must be dictionaries")
                    if not additional_param_vnf.get("member-vnf-index"):
                        raise ValueError("Error at --config 'additionalParamsForVnf' items must contain "
                                         "'member-vnf-index'")
            if "wim_account" in ns_config:
                wim_account = ns_config.pop("wim_account")
                if wim_account is not None:
                    ns['wimAccountId'] = get_wim_account_id(wim_account)
            # rest of parameters without any transformation or checking
            # "timeout_ns_deploy"
            # "placement-engine"
            ns.update(ns_config)

        # print(yaml.safe_dump(ns))
        try:
            self._apiResource = '/ns_instances_content'
            self._apiBase = '{}{}{}'.format(self._apiName,
                                            self._apiVersion, self._apiResource)
            headers = self._client._headers
            headers['Content-Type'] = 'application/yaml'
            http_header = ['{}: {}'.format(key,val)
                          for (key,val) in list(headers.items())]
            self._http.set_http_header(http_header)
            http_code, resp = self._http.post_cmd(endpoint=self._apiBase,
                                   postfields_dict=ns)
            # print('HTTP CODE: {}'.format(http_code))
            # print('RESP: {}'.format(resp))
            #if http_code in (200, 201, 202, 204):
            if resp:
                resp = json.loads(resp)
            if not resp or 'id' not in resp:
                raise ClientException('unexpected response from server - {} '.format(
                                      resp))
            if wait:
                # Wait for status for NS instance creation
                self._wait(resp.get('nslcmop_id'))
            print(resp['id'])
            return resp['id']
            #else:
            #    msg = ""
            #    if resp:
            #        try:
            #            msg = json.loads(resp)
            #        except ValueError:
            #            msg = resp
            #    raise ClientException(msg)
        except ClientException as exc:
            message="failed to create ns: {} nsd: {}\nerror:\n{}".format(
                    nsr_name,
                    nsd_name,
                    str(exc))
            raise ClientException(message)

    def list_op(self, name, filter=None):
        """Returns the list of operations of a NS
        """
        self._logger.debug("")
        ns = self.get(name)
        try:
            self._apiResource = '/ns_lcm_op_occs'
            self._apiBase = '{}{}{}'.format(self._apiName,
                                      self._apiVersion, self._apiResource)
            filter_string = ''
            if filter:
                 filter_string = '&{}'.format(filter)
            http_code, resp = self._http.get2_cmd('{}?nsInstanceId={}'.format(
                                                       self._apiBase, ns['_id'],
                                                       filter_string) )
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            if http_code == 200:
                if resp:
                    resp = json.loads(resp)
                    return resp
                else:
                    raise ClientException('unexpected response from server')
            else:
                msg = resp or ""
            #    if resp:
            #        try:
            #            resp = json.loads(resp)
            #            msg = resp['detail']
            #        except ValueError:
            #            msg = resp
                raise ClientException(msg)
        except ClientException as exc:
            message="failed to get operation list of NS {}:\nerror:\n{}".format(
                    name,
                    str(exc))
            raise ClientException(message)

    def get_op(self, operationId):
        """Returns the status of an operation
        """
        self._logger.debug("")
        self._client.get_token()
        try:
            self._apiResource = '/ns_lcm_op_occs'
            self._apiBase = '{}{}{}'.format(self._apiName,
                                      self._apiVersion, self._apiResource)
            http_code, resp = self._http.get2_cmd('{}/{}'.format(self._apiBase, operationId))
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            if http_code == 200:
                if resp:
                    resp = json.loads(resp)
                    return resp
                else:
                    raise ClientException('unexpected response from server')
            else:
                msg = resp or ""
            #    if resp:
            #        try:
            #            resp = json.loads(resp)
            #            msg = resp['detail']
            #        except ValueError:
            #            msg = resp
                raise ClientException(msg)
        except ClientException as exc:
            message="failed to get status of operation {}:\nerror:\n{}".format(
                    operationId,
                    str(exc))
            raise ClientException(message)

    def exec_op(self, name, op_name, op_data=None, wait=False, ):
        """Executes an operation on a NS
        """
        self._logger.debug("")
        ns = self.get(name)
        try:
            ns = self.get(name)
            self._apiResource = '/ns_instances'
            self._apiBase = '{}{}{}'.format(self._apiName,
                                            self._apiVersion, self._apiResource)
            endpoint = '{}/{}/{}'.format(self._apiBase, ns['_id'], op_name)
            #print('OP_NAME: {}'.format(op_name))
            #print('OP_DATA: {}'.format(json.dumps(op_data)))
            http_code, resp = self._http.post_cmd(endpoint=endpoint, postfields_dict=op_data)
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            #if http_code in (200, 201, 202, 204):
            if resp:
                resp = json.loads(resp)
            if not resp or 'id' not in resp:
                raise ClientException('unexpected response from server - {}'.format(
                                  resp))
            if wait:
                # Wait for status for NS instance action
                # For the 'action' operation, 'id' is used
                self._wait(resp.get('id'))
            return resp['id']
            #else:
            #    msg = ""
            #    if resp:
            #        try:
            #            msg = json.loads(resp)
            #        except ValueError:
            #            msg = resp
            #    raise ClientException(msg)
        except ClientException as exc:
            message="failed to exec operation {}:\nerror:\n{}".format(
                    name,
                    str(exc))
            raise ClientException(message)

    def scale_vnf(self, ns_name, vnf_name, scaling_group, scale_in, scale_out, wait=False):
        """Scales a VNF by adding/removing VDUs
        """
        self._logger.debug("")
        self._client.get_token()
        try:
            op_data={}
            op_data["scaleType"] = "SCALE_VNF"
            op_data["scaleVnfData"] = {}
            if scale_in:
                op_data["scaleVnfData"]["scaleVnfType"] = "SCALE_IN"
            else:
                op_data["scaleVnfData"]["scaleVnfType"] = "SCALE_OUT"
            op_data["scaleVnfData"]["scaleByStepData"] = {
                "member-vnf-index": vnf_name,
                "scaling-group-descriptor": scaling_group,
            }
            op_id = self.exec_op(ns_name, op_name='scale', op_data=op_data, wait=wait)
            print(str(op_id))
        except ClientException as exc:
            message="failed to scale vnf {} of ns {}:\nerror:\n{}".format(
                    vnf_name, ns_name, str(exc))
            raise ClientException(message)

    def create_alarm(self, alarm):
        self._logger.debug("")
        self._client.get_token()
        data = {}
        data["create_alarm_request"] = {}
        data["create_alarm_request"]["alarm_create_request"] = alarm
        try:
            http_code, resp = self._http.post_cmd(endpoint='/test/message/alarm_request',
                                       postfields_dict=data)
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            # if http_code in (200, 201, 202, 204):
            #     resp = json.loads(resp)
            print('Alarm created')
            #else:
            #    msg = ""
            #    if resp:
            #        try:
            #            msg = json.loads(resp)
            #        except ValueError:
            #            msg = resp
            #    raise ClientException('error: code: {}, resp: {}'.format(
            #                          http_code, msg))
        except ClientException as exc:
            message="failed to create alarm: alarm {}\n{}".format(
                    alarm,
                    str(exc))
            raise ClientException(message)

    def delete_alarm(self, name):
        self._logger.debug("")
        self._client.get_token()
        data = {}
        data["delete_alarm_request"] = {}
        data["delete_alarm_request"]["alarm_delete_request"] = {}
        data["delete_alarm_request"]["alarm_delete_request"]["alarm_uuid"] = name
        try:
            http_code, resp = self._http.post_cmd(endpoint='/test/message/alarm_request',
                                       postfields_dict=data)
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            # if http_code in (200, 201, 202, 204):
            #    resp = json.loads(resp)
            print('Alarm deleted')
            #else:
            #    msg = ""
            #    if resp:
            #        try:
            #            msg = json.loads(resp)
            #        except ValueError:
            #            msg = resp
            #    raise ClientException('error: code: {}, resp: {}'.format(
            #                          http_code, msg))
        except ClientException as exc:
            message="failed to delete alarm: alarm {}\n{}".format(
                    name,
                    str(exc))
            raise ClientException(message)

    def export_metric(self, metric):
        self._logger.debug("")
        self._client.get_token()
        data = {}
        data["read_metric_data_request"] = metric
        try:
            http_code, resp = self._http.post_cmd(endpoint='/test/message/metric_request',
                                       postfields_dict=data)
            #print('HTTP CODE: {}'.format(http_code))
            #print('RESP: {}'.format(resp))
            # if http_code in (200, 201, 202, 204):
            #    resp = json.loads(resp)
            return 'Metric exported'
            #else:
            #    msg = ""
            #    if resp:
            #        try:
            #            msg = json.loads(resp)
            #        except ValueError:
            #            msg = resp
            #    raise ClientException('error: code: {}, resp: {}'.format(
            #                          http_code, msg))
        except ClientException as exc:
            message="failed to export metric: metric {}\n{}".format(
                    metric,
                    str(exc))
            raise ClientException(message)

    def get_field(self, ns_name, field):
        self._logger.debug("")
        nsr = self.get(ns_name)
        print(yaml.safe_dump(nsr))
        if nsr is None:
            raise NotFound("failed to retrieve ns {}".format(ns_name))

        if field in nsr:
            return nsr[field]

        raise NotFound("failed to find {} in ns {}".format(field, ns_name))

