from flask import Flask, request, jsonify
import threading
import time
import random
import datetime
import requests
import os

from parameters import processing_graph, machines_tools, TIME_TOOL_CHANGE, MACHINE_PARTNERS, PASS_THROUGH_DURATION_ON_A
from essai import get_shortest_manufacturing_plan

app = Flask(__name__)

JAVA_MES_CALLBACK_URL = os.environ.get("JAVA_MES_CALLBACK_URL", "http://localhost:8081/api/mes/scheduling-callback/step-update")

python_scheduler_machine_states = {}
machine_locks = {}

def initialize_python_machine_states():
    global python_scheduler_machine_states, machine_locks
    for machine_name, tools_list in machines_tools.items():
        python_scheduler_machine_states[machine_name] = {
            "name": machine_name,
            "available_tools": set(tools_list),
            "current_tool": None,
            "busy_until": 0,
        }
        machine_locks[machine_name] = threading.Lock()
    print("[Python-Init] Initialized Python internal machine states for simulation.")

initialize_python_machine_states()


def select_machine_and_calculate_times(operation_detail, current_sequence_time_s):
    required_tool = operation_detail['tool']
    processing_time_s = operation_detail['time']
    
    best_machine_name = None
    earliest_op_finish_time_s = float('inf')
    actual_op_start_time_s_for_best = -1
    tool_change_occurred_for_best = False

    candidate_machine_names = []
    for name, m_data in python_scheduler_machine_states.items():
        if required_tool in m_data["available_tools"]:
            candidate_machine_names.append(name)

    # Sort by: 1. Tool already mounted, 2. Earliest free
    candidate_machine_names.sort(key=lambda m_name:
                                 (0 if python_scheduler_machine_states[m_name]["current_tool"] == required_tool else 1,
                                  python_scheduler_machine_states[m_name]["busy_until"]))

    for machine_name in candidate_machine_names:
        
        machine_free_at_s = python_scheduler_machine_states[machine_name]["busy_until"]
        potential_op_start_on_machine_s = max(current_sequence_time_s, machine_free_at_s)
        
        tool_change_duration_s = 0
        if python_scheduler_machine_states[machine_name]["current_tool"] != required_tool:
            tool_change_duration_s = TIME_TOOL_CHANGE
            
        actual_processing_begins_s = potential_op_start_on_machine_s + tool_change_duration_s
        current_candidate_op_finish_s = actual_processing_begins_s + processing_time_s

        if current_candidate_op_finish_s < earliest_op_finish_time_s:
            earliest_op_finish_time_s = current_candidate_op_finish_s
            actual_op_start_time_s_for_best = actual_processing_begins_s
            best_machine_name = machine_name
            tool_change_occurred_for_best = (tool_change_duration_s > 0)

    if best_machine_name:
        with machine_locks[best_machine_name]:
            if tool_change_occurred_for_best:
                python_scheduler_machine_states[best_machine_name]["current_tool"] = required_tool
            python_scheduler_machine_states[best_machine_name]["busy_until"] = earliest_op_finish_time_s
        return best_machine_name, actual_op_start_time_s_for_best, earliest_op_finish_time_s, tool_change_occurred_for_best
    else:
        return None, -1, -1, False


def opcua_simulation_for_plc_step(machine_name, tool_name, from_piece, to_piece, plc_processing_time_s):
    """Simulates the OPC-UA interaction and PLC processing time."""
    print(f"[Python-OPCUA-SIM] Machine: {machine_name}, Tool: {tool_name}, Op: {from_piece}->{to_piece}, Simulating {plc_processing_time_s}s PLC work...")
    
    time.sleep(plc_processing_time_s)

    if random.random() < 0.02:
        print(f"[Python-OPCUA-SIM] *** SIMULATED PLC STEP FAILURE for {to_piece} on {machine_name} ***")
        return False
        
    print(f"[Python-OPCUA-SIM] Simulated PLC operation for {to_piece} on {machine_name} successful.")
    return True


def background_processing_and_callback(data_from_java_mes):
    mes_order_step_id = data_from_java_mes.get('mesOrderStepId')
    erp_order_item_id = data_from_java_mes.get('erpOrderItemId')
    target_product_str = 'P' + str(data_from_java_mes.get('targetProductType'))

    print(f"[Python-BG] Starting background processing for MES Step ID: {mes_order_step_id}, Target: {target_product_str}")

    manufacturing_plan_steps, _ = get_shortest_manufacturing_plan(processing_graph, target_product_str)

    final_status = "FAILED"
    final_message = f"Processing for MES Step {mes_order_step_id} failed."
    final_timestamp = datetime.datetime.now()


    if not manufacturing_plan_steps:
        final_message = f"No manufacturing plan found for {target_product_str} (MES Step: {mes_order_step_id})"
        print(f"[Python-BG] {final_message}")
    else:
        print(f"[Python-BG] Plan for {target_product_str} (MES ID: {mes_order_step_id}): {len(manufacturing_plan_steps)} operations.")
        
        current_product_instance_time_s = 0
        all_ops_succeeded_for_this_product = True

        for op_idx, operation_detail in enumerate(manufacturing_plan_steps):
            print(f"[Python-BG] MES_ID {mes_order_step_id}: Attempting Op {op_idx+1} ({operation_detail['from_piece']}->{operation_detail['to_piece']} with {operation_detail['tool']})")
            
            selected_machine, op_actual_start_s, op_actual_end_s, tool_changed = select_machine_and_calculate_times(
                operation_detail,
                current_product_instance_time_s
            )

            if not selected_machine:
                final_message = f"Could not find/reserve machine for op {operation_detail['tool']} for {operation_detail['to_piece']} (MES Step: {mes_order_step_id})"
                print(f"[Python-BG] {final_message}")
                all_ops_succeeded_for_this_product = False
                break
            
            print(f"[Python-BG] MES_ID {mes_order_step_id}: Op {operation_detail['to_piece']} assigned to {selected_machine}. "
                  f"Est. Start: {op_actual_start_s}s, Est. End: {op_actual_end_s}s. ToolChange: {tool_changed}")

            operation_time_s = operation_detail['time']
            plc_step_succeeded = opcua_simulation_for_plc_step(
                selected_machine,
                operation_detail['tool'],
                operation_detail['from_piece'],
                operation_detail['to_piece'],
                operation_time_s
            )

            if not plc_step_succeeded:
                final_message = f"Simulated PLC operation failed for {operation_detail['to_piece']} on {selected_machine} (MES Step: {mes_order_step_id})"
                print(f"[Python-BG] {final_message}")
                all_ops_succeeded_for_this_product = False
                break 
            
            current_product_instance_time_s = op_actual_end_s
            final_timestamp = datetime.datetime.fromtimestamp(time.time() - START_TIME_EPOCH + op_actual_end_s) if op_actual_end_s > 0 else datetime.datetime.now()


        if all_ops_succeeded_for_this_product:
            final_status = "COMPLETED"
            final_message = f"MES Step {mes_order_step_id} processing simulated as COMPLETED."
            print(f"[Python-BG] {final_message}")

    result_payload = {
        "mesOrderStepId": mes_order_step_id,
        "erpOrderItemId": erp_order_item_id,
        "status": final_status,
        "timestamp": final_timestamp.isoformat(),
        "errorMessage": final_message if final_status == "FAILED" else None
    }

    print(f"[Python-BG] Sending update to Java MES: {result_payload}")
    try:
        response = requests.post(JAVA_MES_CALLBACK_URL, json=result_payload, timeout=15)
        response.raise_for_status()
        print(f"[Python-BG] Java MES callback successful for {mes_order_step_id}. Status: {response.status_code}")
    except requests.exceptions.RequestException as e_req:
        print(f"[Python-BG] Error calling Java MES callback for {mes_order_step_id}: {e_req}")
    except Exception as e_gen:
        print(f"[Python-BG] Generic error during Java MES callback for {mes_order_step_id}: {e_gen}")


@app.route('/process-step', methods=['POST'])
def process_step_endpoint():
    data = request.json
    if not data or 'mesOrderStepId' not in data or 'erpOrderItemId' not in data or 'targetProductType' not in data:
        return jsonify({"error": "Missing required fields (mesOrderStepId, erpOrderItemId, targetProductType)"}), 400

    print(f"[Python-Flask] Received /process-step request: {data}")

    thread = threading.Thread(target=background_processing_and_callback, args=(data,))
    thread.daemon = True 
    thread.start()

    return jsonify({"message": "Processing initiated for MES Step ID: " + str(data.get('mesOrderStepId'))}), 202


START_TIME_EPOCH = time.time()

if __name__ == '__main__':
    print(f"Starting Python MES Logic Service on port 5001...")
    print(f"Will callback to Java MES at: {JAVA_MES_CALLBACK_URL}")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)