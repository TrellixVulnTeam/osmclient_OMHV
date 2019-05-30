# Copyright 2019 Telefonica
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
OSM API handling for the '--wait' option
"""

from osmclient.common.exceptions import ClientException
import json
from time import sleep
import sys

# Declare a constant for each module, to allow customizing each timeout in the future
TIMEOUT_GENERIC_OPERATION = 600
TIMEOUT_NSI_OPERATION = TIMEOUT_GENERIC_OPERATION
TIMEOUT_SDNC_OPERATION = TIMEOUT_GENERIC_OPERATION
TIMEOUT_VIM_OPERATION = TIMEOUT_GENERIC_OPERATION
TIMEOUT_WIM_OPERATION = TIMEOUT_GENERIC_OPERATION
TIMEOUT_NS_OPERATION = 3600

POLLING_TIME_INTERVAL = 1

MAX_DELETE_ATTEMPTS = 3

def _show_detailed_status(old_detailed_status, new_detailed_status):
    if new_detailed_status is not None and new_detailed_status != old_detailed_status:
        sys.stderr.write("detailed-status: {}\n".format(new_detailed_status))
        return new_detailed_status
    else:
        return old_detailed_status

def _get_finished_states(entity):
    # Note that the member name is either:
    # 'operationState' (NS and NSI)
    # '_admin.'operationalState' (other)
    # For NS and NSI, 'operationState' may be one of:
    # PROCESSING, COMPLETED,PARTIALLY_COMPLETED, FAILED_TEMP,FAILED,ROLLING_BACK,ROLLED_BACK
    # For other entities, '_admin.operationalState' may be one of:
    # operationalState: ENABLED, DISABLED, ERROR, PROCESSING
    if entity == 'NS' or entity == 'NSI':
        return ['COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED_TEMP', 'FAILED']
    else:
        return ['ENABLED', 'ERROR']

def _get_operational_state(resp, entity):
    # Note that the member name is either:
    # 'operationState' (NS)
    # 'operational-status' (NSI)
    # '_admin.'operationalState' (other)
    if entity == 'NS' or entity == 'NSI':
        return resp.get('operationState')
    else:
        return resp.get('_admin', {}).get('operationalState')

def _op_has_finished(resp, entity):
    # _op_has_finished() returns:
    # 0 on success (operation has finished)
    # 1 on pending (operation has not finished)
    # -1 on error (bad response)
    #
    finished_states = _get_finished_states(entity)
    if resp:
        operationalState = _get_operational_state(resp, entity)
        if operationalState:
            if operationalState in finished_states:
                return 0
            return 1
    return -1

def _get_detailed_status(resp, entity, detailed_status_deleted):
    if detailed_status_deleted:
        return detailed_status_deleted
    if entity == 'NS' or entity == 'NSI':
        # For NS and NSI, 'detailed-status' is a JSON "root" member:
        return resp.get('detailed-status')
    else:
        # For other entities, 'detailed-status' a leaf node to '_admin':
        return resp.get('_admin', {}).get('detailed-status')

def _has_delete_error(resp, entity, deleteFlag, delete_attempts_left):
    if deleteFlag and delete_attempts_left:
        state = _get_operational_state(resp, entity)
        if state and state == 'ERROR':
            return True
    return False

def wait_for_status(entity_label, entity_id, timeout, apiUrlStatus, http_cmd, deleteFlag=False):
    # Arguments:
    # entity_label: String describing the entities using '--wait':
    # 'NS', 'NSI', 'SDNC', 'VIM', 'WIM'
    # entity_id: The ID for an existing entity, the operation ID for an entity to create.
    # timeout: See section at top of this file for each value of TIMEOUT_<ENTITY>_OPERATION
    # apiUrlStatus: The endpoint to get the Response including 'detailed-status'
    # http_cmd: callback to HTTP command.
    # Passing this callback as an argument avoids importing the 'http' module here.

    # Loop here until the operation finishes, or a timeout occurs.
    time_left = timeout
    detailed_status = None
    detailed_status_deleted = None
    time_to_return = False
    delete_attempts_left = MAX_DELETE_ATTEMPTS
    try:
        while True:
            http_code, resp_unicode = http_cmd('{}/{}'.format(apiUrlStatus, entity_id))
            resp = ''
            if resp_unicode:
                resp = json.loads(resp_unicode)
            # print 'HTTP CODE: {}'.format(http_code)
            # print 'RESP: {}'.format(resp)
            # print 'URL: {}/{}'.format(apiUrlStatus, entity_id)
            if deleteFlag and http_code == 404:
                # In case of deletion, '404 Not Found' means successfully deleted
                # Display 'detailed-status: Deleted' and return
                time_to_return = True
                detailed_status_deleted = 'Deleted'
            elif http_code not in (200, 201, 202, 204):
                raise ClientException(str(resp))
            if not time_to_return:
                # Get operation status
                op_status = _op_has_finished(resp, entity_label)
                if op_status == -1:
                    # An error occurred
                    raise ClientException('unexpected response from server - {} '.format(
                        str(resp)))
                elif op_status == 0:
                    # If there was an error upon deletion, try again to delete the same instance
                    # If the error is the same, there is probably nothing we can do but exit with error.
                    # If the error is different (i.e. 404), the instance was probably already corrupt, that is,
                    # operation(al)State was probably ERROR before deletion.
                    # In such a case, even if the previous state was ERROR, the deletion was successful,
                    # so detailed-status should be set to Deleted.
                    if _has_delete_error(resp, entity_label, deleteFlag, delete_attempts_left):
                        delete_attempts_left -= 1
                    else:
                        # Operation has finished, either with success or error
                        if deleteFlag:
                            if delete_attempts_left < MAX_DELETE_ATTEMPTS:
                                time_to_return = True
                            delete_attempts_left -= 1
                        else:
                            time_to_return = True
            new_detailed_status = _get_detailed_status(resp, entity_label, detailed_status_deleted)
            if not new_detailed_status:
                new_detailed_status = 'In progress'
            # TODO: Change LCM to provide detailed-status more up to date
            # At the moment of this writing, 'detailed-status' may return different strings
            # from different resources:
            # /nslcm/v1/ns_lcm_op_occs/<id>       ---> ''
            # /nslcm/v1/ns_instances_content/<id> ---> 'deleting charms'
            detailed_status = _show_detailed_status(detailed_status, new_detailed_status)
            if time_to_return:
                return
            time_left -= POLLING_TIME_INTERVAL
            sleep(POLLING_TIME_INTERVAL)
            if time_left <= 0:
                # There was a timeout, so raise an exception
                raise ClientException('operation timeout, waited for {} seconds'.format(timeout))
    except ClientException as exc:
        message="Operation failed for {}:\nerror:\n{}".format(
            entity_label,
            exc.message)
        raise ClientException(message)
