from parameters import *


def get_shortest_manufacturing_plan(graph, target_piece, raw_materials=['P1', 'P2']):
    distances = {node: float('inf') for node in graph}
    # previous_info will store (previous_node, tool_used, time_for_this_step)
    previous_info = {node: None for node in graph}

    for rm_node in raw_materials:
        if rm_node in graph: # Ensure the raw material exists in the graph
            distances[rm_node] = 0

    unvisited_nodes = list(graph.keys())

    while unvisited_nodes:
        current_node = min(unvisited_nodes, key=lambda node: distances[node])

        if distances[current_node] == float('inf'):
            break # Remaining nodes are not reachable

        if current_node == target_piece and distances[current_node] != float('inf'):
             break # Target reached with its optimal path

        for neighbor, (time, tool) in graph[current_node].items():
            # we update the distance if a better path is found.
            new_distance = distances[current_node] + time
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous_info[neighbor] = (current_node, tool, time)
        
        unvisited_nodes.remove(current_node)

    # Reconstruct the plan (sequence of operations)
    if distances[target_piece] == float('inf'):
        return None, float('inf') # No path found

    manufacturing_steps = []
    current_step_target = target_piece
    total_time = distances[target_piece]

    while previous_info[current_step_target] is not None:
        prev_node, tool_used, time_for_step = previous_info[current_step_target]
        manufacturing_steps.append({
            'from_piece': prev_node,
            'to_piece': current_step_target,
            'tool': tool_used,
            'time': time_for_step
        })
        current_step_target = prev_node
    
    manufacturing_steps.reverse() # To have the steps in chronological order
    return manufacturing_steps, total_time

class Machine:
    def __init__(self, name, available_tools):
        self.name = name
        self.available_tools = set(available_tools) # Tools that this machine CAN use
        self.current_tool = None # Currently mounted tool
        self.busy_until = 0 # Time at which the machine becomes free again
        self.current_task_id = None

    def can_perform(self, required_tool): # Changed to accept single tool argument
        return required_tool in self.available_tools

    def assign_task(self, task_op, task_id, current_time):
        """
        Assigns a task to the machine.
        Returns the end time of the task.
        Takes into account tool change time if necessary.
        """
        required_tool = task_op['tool']
        processing_time = task_op['time']
        
        if not self.can_perform(required_tool):
            raise ValueError(f"Machine {self.name} cannot use tool {required_tool}")

        start_time = max(current_time, self.busy_until)
        
        tool_change_duration = 0 # Assume no tool change initially
        if self.current_tool != required_tool:
            tool_change_duration = TIME_TOOL_CHANGE 
            # self.current_tool will be updated by the scheduler *before* this is effectively committed
        
        # Note: The scheduler itself calculates the actual start and end times including tool change.
        # This method might be simplified if the scheduler handles all time calculations.
        # For now, let's keep it reflecting potential logic if called independently.
        # self.busy_until = start_time + tool_change_duration + processing_time
        # self.current_task_id = task_id
        
        # Actual assignment of busy_until and current_tool is done in schedule_production
        task_actual_start_time = start_time + tool_change_duration
        task_end_time = task_actual_start_time + processing_time
        return task_end_time, task_actual_start_time

    def __repr__(self):
        return f"Machine({self.name}, Tool: {self.current_tool}, BusyUntil: {self.busy_until})"

def generate_all_product_instances(order, processing_graph):
    product_instances = []
    instance_counter = 0
    for item in order['orders']:
        product_type_str = 'P' + str(item['type'])
        quantity = item['quantity']
        dDate = item['dDate'] 
        
        for i in range(quantity):
            instance_counter += 1
            product_instance_id = f"{order['orderID']}-{product_type_str}-{i+1}"
            
            manufacturing_plan, total_time = get_shortest_manufacturing_plan(processing_graph, product_type_str)
            if not manufacturing_plan:
                print(f"WARNING: Cannot generate a plan for {product_type_str} (instance {product_instance_id})")
                continue
            
            instance_tasks = []
            for step_idx, step_op in enumerate(manufacturing_plan):
                task_id = f"{product_instance_id}-Op{step_idx+1}"
                instance_tasks.append({
                    'task_id': task_id,
                    'product_instance_id': product_instance_id,
                    'final_product_type': product_type_str,
                    'final_product_ddate': dDate*60, # dDate in seconds
                    'operation': step_op,
                    'dependencies': [f"{product_instance_id}-Op{step_idx}"] if step_idx > 0 else [],
                    'status': 'pending',
                    'assigned_machine': None,
                    'start_time': -1,
                    'end_time': -1,
                    'raw_material_needed': step_op['from_piece']
                })
            product_instances.append({
                'id': product_instance_id,
                'type': product_type_str,
                'ddate': dDate*60, # dDate in seconds
                'tasks': instance_tasks,
                'status': 'pending'
            })
    return product_instances

def schedule_production(order_details, processing_graph_data, machines_data, tool_change_time_val=30):
    global TIME_TOOL_CHANGE # Ensure we are using the global or passed-in one
    TIME_TOOL_CHANGE = tool_change_time_val
    
    # 1. Initialization
    current_time = 0
    shop_floor_machines = {name: Machine(name, tools) for name, tools in machines_data.items()}
    product_instances_to_produce = generate_all_product_instances(order_details, processing_graph_data)
    
    all_tasks_dict = {}
    for inst in product_instances_to_produce:
        for task in inst['tasks']:
            all_tasks_dict[task['task_id']] = task

    if not all_tasks_dict:
        print("No tasks generated for the order.")
        return [], product_instances_to_produce # Early exit if no tasks

    completed_task_ids = set()
    scheduled_history = []

    # 2. Main loop
    while len(completed_task_ids) < len(all_tasks_dict):
        ready_tasks = []
        for task_id, task in all_tasks_dict.items():
            if task['status'] == 'pending':
                deps_met = True
                for dep_id in task['dependencies']:
                    if dep_id not in completed_task_ids:
                        deps_met = False
                        break
                if deps_met:
                    task['status'] = 'ready'
                    # Append a copy if you modify it directly, or append task itself if modification is fine
                    ready_tasks.append(task) 
        
        if not ready_tasks: # No tasks are ready to be scheduled
            all_tasks_done = True # Assume all tasks are done unless a machine is busy or tasks are pending/not done
            min_next_free_time = float('inf')
            has_busy_machine_or_pending_task = False

            for m_eval in shop_floor_machines.values():
                if m_eval.busy_until > current_time:
                    min_next_free_time = min(min_next_free_time, m_eval.busy_until)
                    has_busy_machine_or_pending_task = True # A machine is busy
            
            if not has_busy_machine_or_pending_task: # No machine is busy
                # Check if there are still tasks that are not completed
                if len(completed_task_ids) < len(all_tasks_dict):
                     has_busy_machine_or_pending_task = True # Tasks remain, so we might need to wait or there's a deadlock

            if has_busy_machine_or_pending_task and min_next_free_time != float('inf'):
                current_time = min_next_free_time
                continue
            elif len(completed_task_ids) < len(all_tasks_dict):
                # print(f"WARNING: No tasks ready at time {current_time}, no machines busy, but tasks remain. Deadlock or unfulfillable tasks.")
                break 
            else: # All tasks completed
                break


        ready_tasks.sort(key=lambda t: (t['final_product_ddate'], t['product_instance_id'], t['task_id']))

        task_scheduled_in_this_iteration = False
        for task_to_schedule in ready_tasks:
            if task_to_schedule['status'] != 'ready':
                continue

            required_tool = task_to_schedule['operation']['tool']
            task_processing_time = task_to_schedule['operation']['time']
            
            best_machine_for_task = None
            earliest_finish_time = float('inf')
            calculated_start_time_for_best_machine = -1
            
            mia_partner_for_best_mib = None 
            mia_passthrough_start_for_best_mib = -1
            mia_passthrough_end_for_best_mib = -1

            candidate_machines_sorted = sorted(
                [m for m in shop_floor_machines.values() if m.can_perform(required_tool)],
                key=lambda m_sort: (
                    0 if m_sort.current_tool == required_tool else 1, # Prioritize machines with tool already mounted
                    max(current_time, m_sort.busy_until) # Then by earliest availability
                )
            )

            for machine_candidate in candidate_machines_sorted:
                machine_name = machine_candidate.name
                current_candidate_calculated_start_time = -1
                current_candidate_finish_time = float('inf')
                
                _mia_partner_instance_for_this_candidate = None
                _passthrough_start_on_mia_for_this_candidate = -1
                _passthrough_end_on_mia_for_this_candidate = -1

                tool_change_cost_candidate = 0
                if machine_candidate.current_tool != required_tool:
                    tool_change_cost_candidate = TIME_TOOL_CHANGE

                if machine_name.endswith('a'):
                    machine_can_start_work = max(current_time, machine_candidate.busy_until)
                    actual_processing_start = machine_can_start_work + tool_change_cost_candidate
                    current_candidate_finish_time = actual_processing_start + task_processing_time
                    current_candidate_calculated_start_time = actual_processing_start
                
                elif machine_name.endswith('b'):
                    mia_partner_name = MACHINE_PARTNERS[machine_name]
                    _mia_partner_instance_for_this_candidate = shop_floor_machines[mia_partner_name]

                    _passthrough_start_on_mia_for_this_candidate = max(current_time, _mia_partner_instance_for_this_candidate.busy_until)
                    _passthrough_end_on_mia_for_this_candidate = _passthrough_start_on_mia_for_this_candidate + PASS_THROUGH_DURATION_ON_A
                    
                    mib_can_start_internal_work = max(_passthrough_end_on_mia_for_this_candidate, machine_candidate.busy_until)
                    actual_processing_start = mib_can_start_internal_work + tool_change_cost_candidate
                    current_candidate_finish_time = actual_processing_start + task_processing_time
                    current_candidate_calculated_start_time = actual_processing_start
                
                else: 
                    machine_can_start_work = max(current_time, machine_candidate.busy_until)
                    actual_processing_start = machine_can_start_work + tool_change_cost_candidate
                    current_candidate_finish_time = actual_processing_start + task_processing_time
                    current_candidate_calculated_start_time = actual_processing_start

                if current_candidate_finish_time < earliest_finish_time:
                    earliest_finish_time = current_candidate_finish_time
                    calculated_start_time_for_best_machine = current_candidate_calculated_start_time
                    best_machine_for_task = machine_candidate
                    if machine_name.endswith('b'):
                        mia_partner_for_best_mib = _mia_partner_instance_for_this_candidate
                        mia_passthrough_start_for_best_mib = _passthrough_start_on_mia_for_this_candidate
                        mia_passthrough_end_for_best_mib = _passthrough_end_on_mia_for_this_candidate
                    else: 
                        mia_partner_for_best_mib = None
                        mia_passthrough_start_for_best_mib = -1
                        mia_passthrough_end_for_best_mib = -1

            if best_machine_for_task:
                # Assign task to best_machine_for_task
                if best_machine_for_task.current_tool != required_tool:
                     best_machine_for_task.current_tool = required_tool 
                
                best_machine_for_task.busy_until = earliest_finish_time
                best_machine_for_task.current_task_id = task_to_schedule['task_id']

                task_to_schedule['status'] = 'completed' # Mark task as completed
                task_to_schedule['assigned_machine'] = best_machine_for_task.name
                task_to_schedule['start_time'] = calculated_start_time_for_best_machine
                task_to_schedule['end_time'] = earliest_finish_time
                
                completed_task_ids.add(task_to_schedule['task_id'])
                scheduled_history.append(task_to_schedule.copy()) # Store a copy
                task_scheduled_in_this_iteration = True
                
                if mia_partner_for_best_mib and PASS_THROUGH_DURATION_ON_A > 0:
                    mia_partner_for_best_mib.busy_until = max(mia_partner_for_best_mib.busy_until, mia_passthrough_end_for_best_mib)
                    # mia_partner_for_best_mib.current_task_id = task_to_schedule['task_id'] + "-passthrough_for_" + best_machine_for_task.name
                
                # Since a task was scheduled, we might be able to schedule more in this same current_time slot
                # So, we do not advance current_time here, but rather re-evaluate ready_tasks.
                # The outer loop will continue, and ready_tasks will be repopulated.
                # Consider breaking from 'for task_to_schedule in ready_tasks' to re-evaluate ready_tasks
                # or let it try to schedule other ready tasks at the same current_time.
                # Current logic tries to fill current_time as much as possible.

        if not task_scheduled_in_this_iteration and len(completed_task_ids) < len(all_tasks_dict):
            # If no task was scheduled in this iteration, and tasks still remain,
            # we must advance time to the next moment a machine becomes free.
            min_next_free_time_overall = float('inf')
            any_machine_is_busy = False
            for m_eval in shop_floor_machines.values():
                if m_eval.busy_until > current_time:
                    min_next_free_time_overall = min(min_next_free_time_overall, m_eval.busy_until)
                    any_machine_is_busy = True
            
            if any_machine_is_busy: # If machines are busy, advance time
                current_time = min_next_free_time_overall
            elif len(completed_task_ids) < len(all_tasks_dict): 
                # No task scheduled, no machine busy, but tasks remain -> deadlock or impossible situation
                # print(f"WARNING: Deadlock or unfulfillable tasks at time {current_time}. Remaining tasks: {len(all_tasks_dict) - len(completed_task_ids)}")
                break # Exit loop

    # 3. Results analysis
    print("\n--- Scheduling Finished ---")
    total_makespan = 0
    if scheduled_history:
        for task_details in scheduled_history:
            if task_details['end_time'] > total_makespan : # ensure end_time is valid
                total_makespan = task_details['end_time']
    
    print(f"\nTotal manufacturing time (Makespan): {total_makespan}")

    for p_inst in product_instances_to_produce:
        max_end_time_for_instance = 0 # Initialize with 0 or a known baseline
        all_tasks_completed_for_instance = True
        
        if not p_inst['tasks']: # Product had no manufacturing plan
            p_inst['status'] = 'error_no_plan'
            print(f"Product {p_inst['id']} (Type: {p_inst['type']}) -> ERROR (no manufacturing plan found)")
            continue

        num_instance_tasks = len(p_inst['tasks'])
        completed_instance_tasks_count = 0

        for task_in_plan in p_inst['tasks']:
            task_data = all_tasks_dict.get(task_in_plan['task_id'])
            if task_data and task_data['status'] == 'completed':
                completed_instance_tasks_count += 1
                if task_data['end_time'] > max_end_time_for_instance:
                    max_end_time_for_instance = task_data['end_time']
            else: # Task not found in all_tasks_dict (should not happen if generated correctly) or not completed
                all_tasks_completed_for_instance = False
                # break # No need to break, check all tasks to be sure
        
        if completed_instance_tasks_count < num_instance_tasks:
             all_tasks_completed_for_instance = False


        if all_tasks_completed_for_instance:
            p_inst['completion_time'] = max_end_time_for_instance
            p_inst['status'] = 'completed'
            if p_inst['completion_time'] > p_inst['ddate']:
                p_inst['status'] = 'late'
                print(f"Product {p_inst['id']} (Type: {p_inst['type']}) COMPLETED at {p_inst['completion_time']} (DDate: {p_inst['ddate']}) -> LATE")
            else:
                print(f"Product {p_inst['id']} (Type: {p_inst['type']}) COMPLETED at {p_inst['completion_time']} (DDate: {p_inst['ddate']}) -> ON TIME")
        else:
            p_inst['status'] = 'incomplete'
            print(f"Product {p_inst['id']} (Type: {p_inst['type']}) -> INCOMPLETE ({completed_instance_tasks_count}/{num_instance_tasks} tasks completed)")

    return scheduled_history, product_instances_to_produce


def display_schedule_summary(scheduled_history, product_instances,
                             time_tool_change_val, pass_through_duration_val, machine_partners_val):
    """
    Displays a clear summary of the production schedule.

    Args:
        scheduled_history (list): The history of tasks scheduled by schedule_production.
        product_instances (list): The list of product instances with their final status.
        time_tool_change_val (int): Duration of a tool change.
        pass_through_duration_val (int): Duration of the pass-through on an 'a' machine.
        machine_partners_val (dict): Dictionary of machine partners (e.g., {'M1b': 'M1a'}).
    """
    if not scheduled_history and not product_instances:
        print("No scheduling data to display.")
        return

    print("\n--- Detailed Production Schedule Summary ---")

    all_events = []

    # 1. Prepare all events, including inferred pass-throughs
    for task in scheduled_history:
        # Main task event
        all_events.append({
            'type': 'task',
            'start_time': task['start_time'],
            'end_time': task['end_time'],
            'machine': task['assigned_machine'],
            'task_id': task['task_id'],
            'product_instance_id': task['product_instance_id'],
            'operation': f"{task['operation']['from_piece']} -> {task['operation']['to_piece']} (Tool: {task['operation']['tool']})",
            'duration': task['end_time'] - task['start_time']
        })

        # Infer and add pass-through event if the task is on a 'b' machine
        # and pass-through duration is > 0
        assigned_machine_name = task['assigned_machine']
        if assigned_machine_name.endswith('b') and pass_through_duration_val > 0:
            partner_a_machine_name = machine_partners_val.get(assigned_machine_name)
            if partner_a_machine_name:
                pt_end_time = task['start_time'] # Approximate: ends when B starts its process
                pt_start_time = pt_end_time - pass_through_duration_val

                all_events.append({
                    'type': 'passthrough',
                    'start_time': pt_start_time,
                    'end_time': pt_end_time,
                    'machine': partner_a_machine_name,
                    'task_id': f"PT for {task['task_id']}",
                    'product_instance_id': task['product_instance_id'],
                    'operation': f"Pass-through for {assigned_machine_name}",
                    'duration': pass_through_duration_val
                })

    # 2. Sort all events by start time, then by machine for consistency
    all_events.sort(key=lambda e: (e['start_time'], e['machine']))

    print("\nProduction Event Timeline:")
    print("-" * 100) # Adjusted width for potentially longer English strings
    print(f"{'Time':<15} | {'Machine':<10} | {'Type':<12} | {'Product Instance':<25} | {'Task/Activity':<40}")
    print("-" * 100)

    last_event_time = 0
    for event in all_events:
        if event['start_time'] < 0:  # Do not display invalid events
            continue
        time_str = f"{event['start_time']}-{event['end_time']}"
        print(f"{time_str:<15} | {event['machine']:<10} | {event['type']:<12} | {event['product_instance_id']:<25} | {event['operation']:<40}")
        if event['end_time'] > last_event_time:
            last_event_time = event['end_time']
            
    print("-" * 100)

    # 3. Display summary by product instance
    print("\nSummary by Product Instance:")
    print("-" * 100)
    print(f"{'Product ID':<30} | {'Type':<10} | {'Due Date':<10} | {'Completion':<12} | {'Status':<15} | {'Tardiness':<10}")
    print("-" * 100)

    total_products = len(product_instances)
    completed_products = 0
    late_products = 0
    incomplete_products = 0
    error_products = 0

    for p_inst in product_instances:
        status = p_inst.get('status', 'N/A')
        completion_time = p_inst.get('completion_time', '-')
        tardiness_val = '-'
        
        if status == 'completed' or status == 'late':
            completed_products += 1
            if status == 'late':
                late_products += 1
                tardiness_val = completion_time - p_inst['ddate']
        elif status == 'incomplete':
            incomplete_products += 1
        elif status == 'error_no_plan':
            error_products += 1
            
        completion_str = str(completion_time) if isinstance(completion_time, (int, float)) and completion_time >=0 else "-"
        
        print(f"{p_inst['id']:<30} | {p_inst['type']:<10} | {p_inst['ddate']:<10} | {completion_str:<12} | {status:<15} | {str(tardiness_val):<10}")
    print("-" * 100)

    # 4. Display global statistics
    makespan = 0
    if scheduled_history: # Check if any tasks were scheduled
        for task_details in scheduled_history:
             if task_details['end_time'] > makespan:
                makespan = task_details['end_time']

    print("\nOverall Production Statistics:")
    print("-" * 40)
    print(f"Total Makespan: {makespan}")
    print(f"Total products ordered: {total_products}")
    print(f"Completed products: {completed_products}")
    print(f"  of which late: {late_products}")
    print(f"Incomplete products: {incomplete_products}")
    print(f"Products with errors (no plan): {error_products}")
    print("-" * 40)


print("Initializing data for testing (if necessary)...")
# Execute scheduling
scheduled_history_result, product_instances_result = schedule_production(
    order, 
    processing_graph, 
    machines_tools, 
    TIME_TOOL_CHANGE
)
# Display the enhanced summary
display_schedule_summary(
    scheduled_history_result, 
    product_instances_result,
    TIME_TOOL_CHANGE,
    PASS_THROUGH_DURATION_ON_A, # Must be defined
    MACHINE_PARTNERS             # Must be defined
)

print("\n--- End of Script ---")