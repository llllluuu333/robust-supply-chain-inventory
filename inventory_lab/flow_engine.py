"""High-precision finite-horizon material-flow prototype, not GSM equivalence.

All input quantities are interpreted as their supplied decimal text.  With
JSON, use json.loads(..., parse_float=Decimal) to preserve the JSON number text;
if Python floats are supplied, Decimal(str(value)) describes their printed
round-trip representation, not the original unobserved business quantity.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from decimal import Context, Decimal, Inexact, localcontext, InvalidOperation
import heapq

PRECISION = 50
ZERO = Decimal(0)
CONTEXT = Context(prec=PRECISION)
CONTEXT.traps[Inexact] = True


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value,(int,float,str,Decimal)):
        raise ValueError(f'{label} must be a finite nonnegative decimal')
    try:x=Decimal(str(value))
    except (InvalidOperation, ValueError) as e:raise ValueError(f'{label} is not a decimal') from e
    if not x.is_finite() or x < ZERO or x > Decimal('1e12'):
        raise ValueError(f'{label} is outside the supported decimal range [0,1e12]')
    # Avoid arithmetic with unbounded scales and >50 significant digits.  The
    # external contract is stricter than the internal 50-digit context.
    if x != ZERO and (x.as_tuple().exponent < -30 or len(x.as_tuple().digits)>40):
        raise ValueError(f'{label} has an unsupported number of decimal places or digits')
    return x


def _adjust(box,key,delta):
    old=box[key];new=old+delta
    if not new.is_finite() or new-old!=delta:
        raise ArithmeticError('decimal update exceeds the supported precision')
    box[key]=new


def _remaining(request,delta):
    old=request.remaining;new=old+delta
    if not new.is_finite() or new-old!=delta:
        raise ArithmeticError('decimal request update exceeds the supported precision')
    request.remaining=new


@dataclass
class Request:
    request_id:int
    child:str|None
    remaining:Decimal
    created_day:int


class FlowSimulatorDecimal:
    """FIFO partial fulfillment, unit-input BOM and fixed per-node durations.

    Daily order and planning formula are identical to the float prototype.
    All quantities and cumulative ledgers are Decimal; no customer remainder
    is dropped. A target gap is calculated exactly under the bounded 50-digit
    context; there is no ULP-based target deadband. Each stable event batch is
    audited for exact decimal flow conservation. If an operation exceeds the
    context precision, it raises rather than silently emitting a result.
    """
    def __init__(self,parents,lead_times,targets,max_events_per_day=100000):
        if not isinstance(parents,dict) or not parents:raise ValueError('parents must be a nonempty mapping')
        if any(not isinstance(k,str) or not k for k in parents):raise ValueError('invalid stage names')
        self.nodes=sorted(parents)
        if set(lead_times)!=set(self.nodes) or set(targets)!=set(self.nodes):raise ValueError('lead times and targets must cover exact stages')
        self.parents={}
        for n in self.nodes:
            ps=parents[n]
            if not isinstance(ps,(list,tuple)) or any(not isinstance(p,str) for p in ps):raise ValueError('invalid parent list')
            if len(set(ps))!=len(ps) or any(p not in parents or p==n for p in ps):raise ValueError('invalid parent list')
            self.parents[n]=sorted(ps)
        done=set()
        while len(done)<len(self.nodes):
            ready=[n for n in self.nodes if n not in done and set(self.parents[n])<=done]
            if not ready:raise ValueError('network must be acyclic')
            done.update(ready)
        self.leads={}
        for n in self.nodes:
            t=lead_times[n]
            if type(t) is not int or not 0<=t<=365:raise ValueError('lead times must be integer days in [0,365]')
            self.leads[n]=t
        self.target={n:_number(targets[n],f'target {n}') for n in self.nodes}
        if type(max_events_per_day) is not int or max_events_per_day<1:raise ValueError('max_events_per_day must be positive integer')
        self.max_events=max_events_per_day
        self.H={n:ZERO for n in self.nodes};self.W=dict(self.H);self.P=dict(self.H)
        self.inputs={n:{p:ZERO for p in self.parents[n]} for n in self.nodes}
        self.queues={n:deque() for n in self.nodes}
        self.external_requested=dict(self.H);self.external_on_day=dict(self.H);self.external_delivered=dict(self.H)
        self.requested=dict(self.H);self.shipped=dict(self.H);self.created=dict(self.H)
        self.started=dict(self.H);self.completed=dict(self.H)
        self.received={n:{p:ZERO for p in self.parents[n]} for n in self.nodes}
        self.consumed={n:{p:ZERO for p in self.parents[n]} for n in self.nodes}
        self.pipeline=[];self.request_id=0;self.job_id=0;self.day=0;self.trace=[];self.invalid=False

    def backlog(self,n):
        with localcontext(CONTEXT):return sum((r.remaining for r in self.queues[n]),ZERO)

    def _request(self,n,child,amount):
        if amount<=ZERO:return
        self.request_id+=1
        self.queues[n].append(Request(self.request_id,child,amount,self.day))
        _adjust(self.requested,n,amount)
        if child is None:_adjust(self.external_requested,n,amount)

    def _settle(self):
        with localcontext(CONTEXT):return self._settle_impl()

    def _settle_impl(self):
        operations=0
        while True:
            changes=0
            while self.pipeline and self.pipeline[0][0]<=self.day:
                _,_,n,q=heapq.heappop(self.pipeline)
                _adjust(self.W,n,-q);_adjust(self.completed,n,q);_adjust(self.H,n,q);changes+=1
            for n in self.nodes:
                queue=self.queues[n]
                while queue and self.H[n]>ZERO:
                    req=queue[0];q=min(self.H[n],req.remaining)
                    _adjust(self.H,n,-q);_remaining(req,-q);_adjust(self.shipped,n,q)
                    if req.child is not None:
                        _adjust(self.inputs[req.child],n,q);_adjust(self.received[req.child],n,q)
                    else:
                        _adjust(self.external_delivered,n,q)
                        if req.created_day==self.day:_adjust(self.external_on_day,n,q)
                    if req.remaining==ZERO:queue.popleft()
                    changes+=1
            for n in self.nodes:
                if self.P[n]<=ZERO:continue
                q=min([self.P[n]]+[self.inputs[n][p] for p in self.parents[n]])
                if q<=ZERO:continue
                _adjust(self.P,n,-q);_adjust(self.started,n,q)
                for parent in self.parents[n]:_adjust(self.inputs[n],parent,-q);_adjust(self.consumed[n],parent,q)
                if self.leads[n]==0:_adjust(self.completed,n,q);_adjust(self.H,n,q)
                else:
                    _adjust(self.W,n,q);self.job_id+=1
                    heapq.heappush(self.pipeline,(self.day+self.leads[n],self.job_id,n,q))
                changes+=1
            for n in self.nodes:
                ip=self.H[n]+self.W[n]+self.P[n]-self.backlog(n)
                q=self.target[n]-ip
                if q<=ZERO:continue
                _adjust(self.P,n,q);_adjust(self.created,n,q)
                for parent in self.parents[n]:self._request(parent,n,q)
                changes+=1
            operations+=changes
            if operations>self.max_events:raise RuntimeError('daily event limit exceeded')
            if not changes:break
        self._audit()

    def _audit(self):
        with localcontext(CONTEXT):return self._audit_impl()

    def _audit_impl(self):
        def same(a,b,label):
            if a!=b:raise RuntimeError(f'decimal conservation violation: {label}')
        for n in self.nodes:
            for x in (self.H[n],self.W[n],self.P[n],self.backlog(n)):
                if not x.is_finite() or x<ZERO:raise RuntimeError(f'invalid decimal state: {n}')
            same(self.completed[n],self.H[n]+self.shipped[n],f'{n} output')
            same(self.started[n]-self.completed[n],self.W[n],f'{n} work in progress')
            same(self.created[n]-self.started[n],self.P[n],f'{n} planned')
            same(self.requested[n]-self.shipped[n],self.backlog(n),f'{n} backlog')
            for p in self.parents[n]:
                if self.inputs[n][p]<ZERO:raise RuntimeError(f'negative input: {n} {p}')
                same(self.received[n][p]-self.consumed[n][p],self.inputs[n][p],f'{n}.{p} input')
                same(self.consumed[n][p],self.started[n],f'{n}.{p} BOM usage')
                outstanding=sum((r.remaining for r in self.queues[p] if r.child==n),ZERO)
                same(self.received[n][p]+outstanding,self.created[n],f'{n}.{p} input orders')
            same(sum((j[3] for j in self.pipeline if j[2]==n),ZERO),self.W[n],f'{n} pipeline')
            child=sum((self.received[c][n] for c in self.nodes if n in self.parents[c]),ZERO)
            same(self.shipped[n],self.external_delivered[n]+child,f'{n} cross-edge shipments')
            external=sum((r.remaining for r in self.queues[n] if r.child is None),ZERO)
            same(self.external_requested[n]-self.external_delivered[n],external,f'{n} external orders')

    def step(self,demand):
        if self.invalid:raise RuntimeError('simulator cannot continue after failure')
        if not isinstance(demand,dict) or any(n not in self.nodes for n in demand):raise ValueError('unknown demand node')
        quantities={n:_number(demand.get(n,0),f'demand {n}') for n in self.nodes}
        self.external_on_day={n:ZERO for n in self.nodes}
        try:
            with localcontext(CONTEXT):
                self._settle_impl()
                for n in self.nodes:self._request(n,None,quantities[n])
                self._settle_impl()
                state={'day':self.day,'demand':quantities,'on_day_fulfilled':dict(self.external_on_day),
                  'on_hand':dict(self.H),'work_in_process':dict(self.W),'waiting_plan':dict(self.P),
                  'backlog':{n:self.backlog(n) for n in self.nodes},
                  'input_stock':{n:dict(self.inputs[n]) for n in self.nodes},
                  'target_shortfall':{n:max(ZERO,self.target[n]-(self.H[n]+self.W[n]+self.P[n]-self.backlog(n))) for n in self.nodes},
                  'cumulative':{'requested':dict(self.requested),'shipped':dict(self.shipped),
                    'planned':dict(self.created),'started':dict(self.started),'completed':dict(self.completed),
                    'external_requested':dict(self.external_requested),'external_delivered':dict(self.external_delivered),
                    'received':{n:dict(self.received[n]) for n in self.nodes},
                    'consumed':{n:dict(self.consumed[n]) for n in self.nodes}}}
                self.trace.append(state);self.day+=1
                return state
        except (RuntimeError,ArithmeticError):self.invalid=True;raise

    def run(self,demands):
        for row in demands:self.step(row)
        return self.trace


def decimal_to_jsonable(value):
    """Recursively encode Decimal as exact decimal strings for JSON output."""
    if isinstance(value,Decimal):
        if not value.is_finite():raise ValueError('non-finite Decimal cannot be serialized')
        return str(value)
    if isinstance(value,dict):return {k:decimal_to_jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [decimal_to_jsonable(v) for v in value]
    return value


