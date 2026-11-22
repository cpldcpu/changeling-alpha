"""Behavioural model of the line cell, one call of step() per time unit.
Used to check the rules of the specification, not cycle-accurate RTL."""
class Cell:
    def __init__(s, **cfg):
        d=dict(RXEN=0,TXEN=0,EDGE=0,ACC=0,STOP=0,TWOPH=0,TRIG=0,A=1,B=1,C=1,DEC=0xF0,ENC=0xF0,
               LEN=7,LSBF=0,CMP=0,MEN=0,SS=0,MATCH=0,LIM=0,RMODE=0,IDLE=0,CPHA=0,CPOL=0,BLEN=0,LOW2=0,PAR=0)
        d.update(cfg); s.__dict__.update(d)
        s.state='WAIT'; s.T=0; s.ph=0; s.prev=0; s.last=None; s.quiet=True; s.qcnt=0; s.tw=0
        s.n=0; s.win=[0]*8; s.run=0; s.lastd=None; s.skip=False; s.hn=0
        s.hunt=bool(s.MEN); s.ext=False; s.xv=0; s.FERR=0; s.txbuf9=0
        s.fifo=[]; s.frames=[]; s.OVR=s.STUFF=s.MATCHF=s.IDLEF=s.EOPF=0; s.bothl=0
        s.txbuf=None; s.busy=False; s.tq=[]; s.out=s.IDLE; s.prevout=s.IDLE; s.clk=s.CPOL
        s.cur=0; s.ttx=0; s.trun=0; s.tlast=None; s.stage=None; s.tbits=[]
        s.log=[]; s.samples=[]; s.edges=[]; s.t=0; s.refev=[]
    # ---------------- receive ----------------
    def _val(s,bits):
        v=0
        for i,b in enumerate(bits):
            v |= (b<<i) if s.LSBF else (b<<(len(bits)-1-i))
        return v
    def _rxreset(s):
        s.n=0; s.run=0; s.lastd=None; s.skip=False; s.hunt=bool(s.MEN); s.hn=0; s.ext=False
    def _push(s,v):
        if len(s.fifo)>=2: s.OVR=1
        else: s.fifo.append(v)
    def _sample(s,x,ph):
        d=(s.DEC>>((x<<2)|(s.prev<<1)|ph))&1
        s.prev=x; s.samples.append(s.t)
        if s.LIM:
            if s.skip:
                s.skip=False
                if s.RMODE==0:
                    if d==1: s.STUFF=1
                    s.run=0
                else:
                    if d==s.lastd: s.STUFF=1
                    s.run=1; s.lastd=d
                return False
            if s.RMODE==0: s.run = s.run+1 if d==1 else 0
            else:
                s.run = s.run+1 if d==s.lastd else 1
                s.lastd=d
            if s.run==s.LIM: s.skip=True
        if s.ext:                                   # additional bit (C7): after the data bits, not in the window
            s.ext=False; s.n=0; ones=bin(s.xv).count('1')+d
            if (s.PAR==1 and ones%2==0) or (s.PAR==2 and ones%2==1): s.FERR=1
            s._push(s.xv|d<<8); return True
        s.win=(s.win+[d])[-8:]; s.n+=1; s.hn=min(8,s.hn+1)
        if s.hunt:
            if s.hn==8 and s._val(s.win)==s.MATCH:      # eight bits since the receiver reset (rule R9)
                s.MATCHF=1; s.hunt=False; s.n=0
            return False
        if s.n==s.LEN+1:
            v=s._val(s.win[-(s.LEN+1):]); s.n=0
            if s.PAR: s.xv=v; s.ext=True; return False
            s._push(v)
            return True
        return False
    def read(s):
        return s.fifo.pop(0) if s.fifo else None
    def step(s,x=0,x2=1):
        """x: filtered input pin level, x2: filtered second pin level. Returns (out, second_out)."""
        if s.last is None: s.last=x
        if s.RXEN:
            bl = 1 if (s.BLEN and x==0 and x2==0) else 0
            if bl and not s.bothl:
                s.refev.append((s.t,'bothl', s.quiet))
                s.EOPF=1                      # stored flag: both pins have gone low
                s.state='WAIT'; s.tw=0; s._rxreset()
            s.bothl=bl
            rise = x==1 and s.last==0; fall = x==0 and s.last==1
            edge = (rise and s.EDGE in (1,3)) or (fall and s.EDGE in (2,3))
            acc = edge and not bl and (s.ACC==0 or s.state=='WAIT')
            if acc:
                if s.state=='WAIT': s.prev=s.last
                s.T=s.A if s.A else 256; s.state='RUN'; s.ph=0; s.quiet=False; s.qcnt=0
                s.edges.append(s.t)
            elif s.state=='RUN' and s.TRIG==0:
                s.T-=1
                if s.T==0:
                    done=False; sampled=False
                    if s.STOP==0:
                        s.qcnt+=1
                    if s.STOP==0 and s.qcnt==8:
                        s.IDLEF=1; s.quiet=True; s.state='WAIT'; s._rxreset()
                    else:
                        ph=s.ph
                        if s.TWOPH:
                            lead=(s.ph==0); s.ph^=1; do=(lead==(s.CPHA==0))
                        else: do=True
                        if do: done=s._sample(x,ph); sampled=True
                        if (s.STOP==1 and sampled) or (s.STOP==2 and done):
                            s.state='WAIT'; s.tw=s.B if s.B else 256
                        else: s.T=s.B if s.B else 256
            elif s.state=='WAIT' and s.STOP!=0 and s.tw>0:
                s.tw-=1
                if s.tw==0:
                    s.IDLEF=1; s.quiet=True; s._rxreset()
        s.last=x
        o=s._tx()
        s.t+=1
        return o
    # ---------------- transmit ----------------
    def write(s,v):
        assert s.txbuf is None; s.txbuf=v&255; s.txbuf9=(v>>8)&1
    @property
    def TXE(s): return s.txbuf is None
    def _load(s):
        v=s.txbuf; s.txbuf=None
        bits=[(v>>i)&1 if s.LSBF else (v>>(s.LEN-i))&1 for i in range(s.LEN+1)]
        if s.PAR==3: bits.append(s.txbuf9)
        elif s.PAR: bits.append((sum(bits)+(s.PAR==1))&1)
        s.tq=([('d',1-s.IDLE,False)] if s.SS else [])+[('d',b,True) for b in bits]+([('d',s.IDLE,False)] if s.SS else [])
    def _next(s):
        """next symbol to send, with stuffing; None at end of frame"""
        if s.LIM and s.trun==s.LIM:
            b = 0 if s.RMODE==0 else 1-s.tlast
            s.trun = 0 if s.RMODE==0 else 1
            s.tlast=b; return b
        if not s.tq:
            if s.txbuf is None: return None
            s._load()
        _,b,data=s.tq.pop(0)
        if s.LIM and data:
            if s.RMODE==0: s.trun = s.trun+1 if b==1 else 0
            else: s.trun = s.trun+1 if b==s.tlast else 1
            s.tlast=b
        return b
    def _enc(s):
        if s.CMP: return
        s.out=(s.ENC>>((s.cur<<2)|(s.ph<<1)|s.prevout))&1; s.prevout=s.out
    def _tx(s):
        if not s.TXEN: return (s.IDLE,s.IDLE)
        if not s.busy:
            if s.txbuf is not None:
                s.busy=True; s.trun=0; s.tlast=None; s.tq=[]; s.ph=0
                s.cur=s._next(); s.ttx=s.B; s.prevout=s.out; s._enc(); s.tbits.append(s.cur)
        else:
            s.ttx-=1
            if s.ttx==0:
                s.ttx=s.B; adv=True
                if s.TWOPH:
                    if s.ph==0: s.ph=1; adv=False
                    else: s.ph=0
                if adv:
                    nb=s._next()
                    if nb is None:
                        s.busy=False; s.out=s.IDLE; s.prevout=s.IDLE; s.ph=0
                    else: s.cur=nb; s.tbits.append(nb)
                if s.busy: s._enc()
        if s.busy and s.CMP:
            s.out = 1 if (s.B-s.ttx) < (s.A if s.cur else s.C) else 0
        if s.LOW2: return (0,0)
        if not s.busy: return (s.IDLE,s.IDLE)
        s.clk = s.CPOL ^ s.ph
        return (s.out, 1-s.out)
