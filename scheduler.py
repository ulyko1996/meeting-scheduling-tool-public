import streamlit as st
import json
from ortools.sat.python import cp_model

st.title('Meeting scheduling app')
st.write('''
The schedule is made based on the following constraints:
- Each member can only attend one meeting at each timeslot
- Each meeting must be attended by at least two members with the corresponding role.
- Pre-scheduled meetings must be attended by all members with the corresponding role, except for the absent member(s). Otherwise one member is allowed to miss it.
- At least one meeting must be scheduled for each role, except when there is no or only one member present for that role. In that case, no meetings will be scheduled for that role.
''')

with open('roles_employees.json') as f:
    roles_employees = json.load(f)

employees = set([item for sublist in roles_employees.values() for item in sublist])

n_blocks = st.number_input('Input the number of blocks you want', value=4)
absent_colleagues = st.multiselect('Please select colleague(s) that will not be present on that day.', list(employees))
fixed_meetings = [st.multiselect('Please select the group(s) that must have a meeting in Block ' + str(n+1), list(roles_employees.keys())) for n in range(n_blocks)]
#n_meetings = [st.select_slider('Please select the range of number of meetings for ' + role, options=range(1, n_blocks+1), value=(1,1)) for role in roles_employees.keys()]

def main(n_blocks, absent_colleagues):
    model = cp_model.CpModel()

    # Define variables
    timeslots = ['Block ' + str(n+1) for n in range(int(n_blocks))]

    # Remove absent colleagues
    if len(absent_colleagues) > 0:
        _roles_employees_without_absentee = {}
        for role in roles_employees:
            _roles_employees_without_absentee[role] = list(filter(lambda x: True if x not in absent_colleagues else False, roles_employees[role]))
    else:
        _roles_employees_without_absentee = roles_employees

    # Convert variables into numbers
    _timeslots = range(0, len(timeslots))
    _roles = range(0, len(_roles_employees_without_absentee))
    _employees = set([item for sublist in _roles_employees_without_absentee.values() for item in sublist])
    _employees_idx = range(0, len(_employees))
    _indices_employees = dict(enumerate(_employees))
    _revs_indices_employees = {v:k for k,v in _indices_employees.items()}

    _roles_employees = {}
    for idx, role in enumerate(_roles_employees_without_absentee):
        _roles_employees[idx] = [_revs_indices_employees.get(item, item) for item in _roles_employees_without_absentee[role]]

    # Create shifts
    shifts = {}
    for t in _timeslots:
        for r in _roles_employees.keys():
            for e in _roles_employees.get(r):
                shifts[(t,r,e)] = model.NewBoolVar('shift_t%ir%ie%i' % (t,r,e))

    # Create constraints
    # 1. All employees can only be in one role at each timeslot
    for e in _employees_idx:
        for t in _timeslots:
            model.AddAtMostOne(shifts[(t,r,e)] for r in [k for k,v in _roles_employees.items() if e in v])

    # 2. All roles have at least one timeslot allocated to it
    for idx, r in enumerate(_roles_employees.keys()):
        if r != 8: # Except Role 9
            timeslots_assigned = []
            n_employees = len(_roles_employees[r])
            for t in _timeslots:
                for e in _roles_employees[r]:
                    timeslots_assigned.append(shifts[(t,r,e)])
            if n_employees > 1: # Except when there is no one or only one member present
                model.Add(sum(timeslots_assigned) > 0)
            else:
                model.Add(sum(timeslots_assigned) == 0)

    # 3. All members of the same role have to stick together
    for r in _roles_employees.keys():
        n_employees = len(_roles_employees[r])
        for t in _timeslots:
            shifts_assigned = []
            for e in _roles_employees[r]:
                shifts_assigned.append(shifts[(t,r,e)])
            model.AddLinearExpressionInDomain(sum(shifts_assigned), cp_model.Domain.FromValues([0, max(2, n_employees - 1), n_employees]))

    # 4. Specific timeslots are pre-filled
    def add_constraint(t,r, value):
        for e in _roles_employees[r-1]:
            model.Add(shifts[(t,r-1,e)] == value)

    for t_idx, r_list in enumerate(fixed_meetings):
        for r in r_list:
            add_constraint(t_idx, int(r[-1]), 1)
        if 'Role 9' not in r_list:
            add_constraint(t_idx, 9, 0)

    # Frame as optimization problem
    total_shifts = []
    for t in _timeslots:
        for r in _roles_employees.keys():
            for e in _roles_employees.get(r):
                total_shifts.append(shifts[(t,r,e)])

    total_roles = []
    for t in _timeslots:
        for r in _roles_employees.keys():
            tmp = model.NewBoolVar('role_t%ir%i' % (t,r))
            model.Add(sum([shifts[(t,r,e)] for e in _roles_employees.get(r)]) > 0).OnlyEnforceIf(tmp)
            model.Add(sum([shifts[(t,r,e)] for e in _roles_employees.get(r)]) == 0).OnlyEnforceIf(tmp.Not())
            total_roles.append(tmp)
    
    model.Maximize(sum(total_shifts) - sum(total_roles) * 0.1)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if solver.StatusName(status) == 'INFEASIBLE':
        st.write('The program cannot find a solution that satisfies all your requirements. Please remove one of them.')
    else:
        for t in _timeslots:
            st.header('%s' % (timeslots[t]))
            chosen_employees = []
            for r in _roles_employees:
                role = list(roles_employees.keys())[r]
                chosen_members = []
                for e in _roles_employees[r]:
                    if solver.Value(shifts[(t,r,e)]):
                        chosen_members.append(_indices_employees[e])
                if len(chosen_members) > 0:
                    st.markdown(':arrow_forward: **%s:** %s' % (role, ', '.join(chosen_members)))
                    chosen_employees.extend(chosen_members)
            st.write('Employees left:', ', '.join(list(_employees - set(chosen_employees))))

main(n_blocks, absent_colleagues)