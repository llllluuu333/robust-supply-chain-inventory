"""General network fixed-decision finite-scenario guaranteed-service MILP.

Adapted from the case-01 research implementation; topology is supplied by the user.
Outputs are research model values only.
"""
from __future__ import annotations
import math
import sys
import time
from collections import deque
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
class InputError(ValueError):
    pass

SCHEMA = 'inventory_lab.network.robust.v1'



def _is_real_nonnegative(value):
    if type(value) not in (int,float):return False
    try:return math.isfinite(value) and value >= 0
    except OverflowError:return False


def _validated(data):
    if not isinstance(data,dict) or data.get('schema_version')!=SCHEMA:
        raise InputError('Unsupported robust network schema version')
    if data.get('time_unit') not in ('assumed_business_day','calendar_day','synthetic_day'):
        raise InputError('Specify a supported time_unit')
    names=data.get('nodes')
    if not isinstance(names,list) or not 1<=len(names)<=32 or any(not isinstance(x,str) or not x.strip() for x in names) or len(set(names))!=len(names):
        raise InputError('Nodes must be 1 to 32 unique nonempty names')
    n=len(names);idx={x:i for i,x in enumerate(names)}
    edges=data.get('edges')
    if not isinstance(edges,list) or len(edges)>128 or any(not isinstance(x,list) or len(x)!=2 or any(not isinstance(y,str) or y not in idx for y in x) or x[0]==x[1] for x in edges):
        raise InputError('Invalid edges')
    if len(set(map(tuple,edges)))!=len(edges):
        raise InputError('Duplicate edges')
    weights=data.get('weights')
    if not isinstance(weights,list) or len(weights)!=n or any(not _is_real_nonnegative(x) for x in weights):
        raise InputError('Case01 weights must be finite nonnegative numbers')
    scenarios=data.get('scenarios')
    if not isinstance(scenarios,list) or not 1<=len(scenarios)<=16:
        raise InputError('Provide between 1 and 16 finite scenarios')
    seen=set();times=[]
    for scenario in scenarios:
        if not isinstance(scenario,dict):raise InputError('Invalid scenario')
        name=scenario.get('name');T=scenario.get('T')
        if not isinstance(name,str) or not name.strip() or len(name)>64 or name in seen:raise InputError('Scenario names must be unique nonempty strings of at most 64 characters')
        if not isinstance(T,list) or len(T)!=n or any(type(x) is not int or not 0<=x<=365 for x in T):
            raise InputError('Scenario processing times must be integer days in [0,365]')
        seen.add(name);times.append(T)
    caps=data.get('source_service_caps')
    if not isinstance(caps,dict) or any(k not in idx for k in caps) or any(type(x) is not int or not 0<=x<=365 for x in caps.values()):
        raise InputError('Source service caps must map source node names to integer days in [0,365]')
    parents={x:[] for x in names};children={x:[] for x in names}
    for a,b in edges:parents[b].append(a);children[a].append(b)
    if any(parents[x] for x in caps):raise InputError('Service caps may only be specified on source nodes')
    todo={x:len(parents[x]) for x in names};queue=deque(x for x in names if todo[x]==0);order=[]
    while queue:
        x=queue.popleft();order.append(x)
        for y in children[x]:
            todo[y]-=1
            if todo[y]==0:queue.append(y)
    if len(order)!=n:raise InputError('Network must be acyclic')
    maxT=[max(t[i] for t in times) for i in range(n)];M={}
    for x in order:M[x]=maxT[idx[x]]+max((M[y] for y in parents[x]),default=0)
    if max(M.values())>365:raise InputError('Maximum protection horizon exceeds 365 integer days')
    curves=data.get('curves')
    if not isinstance(curves,list) or len(curves)!=n:raise InputError('Provide one demand buffer curve per node')
    for i,x in enumerate(names):
        curve=curves[i];needed=M[x]+1
        if not isinstance(curve,list) or len(curve)<needed or len(curve)>366 or any(not _is_real_nonnegative(v) for v in curve):
            raise InputError(f'Invalid or insufficient curve for {x}')
        if curve[0]!=0 or any(curve[k+1]<curve[k] for k in range(len(curve)-1)):
            raise InputError(f'Curve for {x} must start at zero and be nondecreasing')
        if any(not math.isfinite(weights[i]*v) for v in curve[:needed]):
            raise InputError(f'Non-finite weighted curve for {x}')
    try:
        maximum_possible=math.fsum(weights[i]*curves[i][M[x]] for i,x in enumerate(names))
    except OverflowError as exc:raise InputError('Non-finite total objective bound') from exc
    if not math.isfinite(maximum_possible):raise InputError('Non-finite total objective bound')
    # HiGHS drops very small matrix coefficients. Reject unsupported within-model
    # dynamic ranges instead of silently changing the optimized objective.
    weighted=[]
    for i,x in enumerate(names):
        for v in curves[i][:M[x]+1]:
            product=weights[i]*v
            if weights[i]>0 and v>0 and product==0:
                raise InputError('Weighted curve underflows floating-point range')
            if product>0:weighted.append(product)
    if maximum_possible>0 and maximum_possible<sys.float_info.min:
        raise InputError('Objective scale is subnormal and unsupported')
    if weighted and any(value/maximum_possible<1e-5 for value in weighted):
        raise InputError('Weighted curve dynamic range exceeds the supported numerical range')
    return names,idx,edges,parents,children,times,maxT,[M[x] for x in names],maximum_possible


def validate(data):
    """Reject invalid or incompatible inputs before constructing a MILP."""
    _validated(data)


def solve(data,time_limit=60.):
    """Solve min over shared integer service times of max scenario buffer cost.

    Every scenario has its own protection-period variables and constraints; the
    service times are common. No assumption of a single worst scenario is made.
    """
    names,idx,edges,parents,children,times,maxT,M,maximum_possible=_validated(data)
    objective_scale=maximum_possible if maximum_possible>0 else 1.0
    if type(time_limit) not in (int,float) or not math.isfinite(time_limit) or not 0<time_limit<=3600:
        raise InputError('Time limit must be in (0,3600]')
    n=len(names);offsets=[];size=2*n
    for _ in times:
        off=[]
        for m in M:off.append(size);size+=m+1
        offsets.append(off)
    epigraph=size;size+=1
    objective=np.zeros(size);objective[epigraph]=1.
    lo=np.zeros(size);hi=np.full(size,np.inf);integrality=np.ones(size,int);integrality[epigraph]=0
    for i,name in enumerate(names):
        hi[i]=M[i]-maxT[i];hi[n+i]=M[i]
        if not parents[name]:hi[i]=0
        if not children[name]:hi[n+i]=0
        if name in data['source_service_caps']:hi[n+i]=min(hi[n+i],data['source_service_caps'][name])
    for off in offsets:
        for i,m in enumerate(M):hi[off[i]:off[i]+m+1]=1
    A=lil_matrix((len(times)*(2*n+1)+len(edges),size));lb=np.full(A.shape[0],-np.inf);ub=np.full(A.shape[0],np.inf);row=0
    for k,T in enumerate(times):
        for i,m in enumerate(M):
            span=slice(offsets[k][i],offsets[k][i]+m+1)
            A[row,span]=1;lb[row]=ub[row]=1;row+=1
            A[row,i]=1;A[row,n+i]=-1;A[row,span]=-np.arange(m+1);lb[row]=ub[row]=-T[i];row+=1
        for i,m in enumerate(M):
            A[row,offsets[k][i]:offsets[k][i]+m+1]=np.asarray([data['weights'][i]*v/objective_scale for v in data['curves'][i][:m+1]])
        A[row,epigraph]=-1;ub[row]=0;row+=1
    for a,b in edges:A[row,n+idx[a]]=1;A[row,idx[b]]=-1;ub[row]=0;row+=1
    assert row==A.shape[0]
    start=time.perf_counter()
    res=milp(objective,integrality=integrality,bounds=Bounds(lo,hi),constraints=LinearConstraint(A.tocsr(),lb,ub),options={'time_limit':float(time_limit),'mip_rel_gap':0.0,'threads':1})
    def finite(value):return float(value) if value is not None and math.isfinite(value) else None
    def unscale(value):
        value=finite(value)
        if value is None:return None
        result=value*objective_scale
        return result if math.isfinite(result) else None
    reported_gap=finite(getattr(res,'mip_gap',None))
    accepted_optimal=(res.status==0 and reported_gap is not None and 0<=reported_gap<=1e-8)
    out={'status':int(res.status),'message':str(res.message),'solver_reported_optimal':res.status==0,
         'optimal':accepted_optimal,'has_solution':res.x is not None,'objective':unscale(res.fun),'dual_bound':unscale(getattr(res,'mip_dual_bound',None)),
         'mip_gap':reported_gap,'time_seconds':time.perf_counter()-start,
         'variables':size,'constraints':row,'nodes':names,'time_unit':data['time_unit'],'max_horizon':M,'scenario_names':[s['name'] for s in data['scenarios']],'objective_scale':objective_scale}
    if res.x is None:
        if out['solver_reported_optimal']:raise RuntimeError('Solver reported optimality without a solution')
        return out
    if not np.all(np.isfinite(res.x[:2*n])) or np.max(np.abs(res.x[:2*n]-np.rint(res.x[:2*n])))>1e-5:
        raise RuntimeError('Solver produced invalid service times')
    si=np.rint(res.x[:n]).astype(int);S=np.rint(res.x[n:2*n]).astype(int)
    if any(si[i]<0 or si[i]>M[i]-maxT[i] or S[i]<0 or S[i]>M[i] for i in range(n)):
        raise RuntimeError('Solver produced a decision outside service-time bounds')
    if any(si[idx[x]]!=0 for x in names if not parents[x]) or any(S[idx[x]]!=0 for x in names if not children[x]) or any(S[idx[a]]>si[idx[b]] for a,b in edges):
        raise RuntimeError('Solver decision violates network constraints')
    if any(S[idx[x]]>cap for x,cap in data['source_service_caps'].items()):raise RuntimeError('Solver decision violates source cap')
    costs=[];protection=[]
    for s,T in zip(data['scenarios'],times):
        tau=[int(si[i])+T[i]-int(S[i]) for i in range(n)]
        if any(t<0 or t>M[i] for i,t in enumerate(tau)):raise RuntimeError('Solver decision infeasible in a scenario')
        value=math.fsum(float(data['weights'][i]*data['curves'][i][tau[i]]) for i in range(n))
        if not math.isfinite(value):raise RuntimeError('Non-finite scenario objective')
        costs.append({'name':s['name'],'objective':value});protection.append({'name':s['name'],'days':tau})
    worst=max(x['objective'] for x in costs)
    # Check in normalized units, so a fixed absolute tolerance cannot hide
    # incorrect values when the original objective is very small.
    normalized_worst=worst/objective_scale
    if out['objective'] is None or not math.isfinite(normalized_worst) or res.fun+1e-9+1e-7*abs(normalized_worst)<normalized_worst:
        raise RuntimeError('Solver epigraph is below reconstructed worst objective')
    if out['optimal'] and not math.isclose(res.fun,normalized_worst,rel_tol=1e-7,abs_tol=1e-9):
        raise RuntimeError('Optimal objective does not match reconstructed worst objective')
    normalized_bound=finite(getattr(res,'mip_dual_bound',None))
    bound_consistent=(normalized_bound is not None and normalized_bound<=normalized_worst+1e-9+1e-7*abs(normalized_worst))
    out['solver_dual_bound']=out['dual_bound']
    out['bound_consistent']=bound_consistent
    if not bound_consistent:
        # Keep the feasible decision for inspection, but do not advertise a
        # missing or contradictory solver bound as a valid certificate.
        out['dual_bound']=None
        reconstructed_gap=None
    else:
        # For zero cost, nonnegative coefficients and a feasible witness establish
        # the theoretical lower bound zero; otherwise use the actual positive
        # reconstructed objective as the relative-gap denominator.
        reconstructed_gap=0.0 if normalized_worst==0 else max(0.,normalized_worst-normalized_bound)/abs(normalized_worst)
    # Preserve solver status but do not certify a result when its reconstructed
    # primal-versus-dual gap is missing or exceeds our reporting threshold.
    out['reconstructed_relative_gap']=reconstructed_gap
    if reconstructed_gap is None or reconstructed_gap>1e-7:out['optimal']=False
    out.update({'SI':[int(x) for x in si],'S':[int(x) for x in S],
                'scenario_costs':costs,'protection_periods':protection,'recomputed_worst':worst})
    return out