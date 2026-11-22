import sys; sys.path.insert(0,'.')
from linecell import Cell
def run_tx(cell, data, tail=40):
    """send bytes gapless; returns list of (out, second) per unit"""
    w=[]; q=list(data)
    for _ in range(100000):
        if q and cell.TXE: cell.write(q.pop(0))
        w.append(cell.step())
        if not q and cell.TXE and not cell.busy: break
    for _ in range(tail): w.append(cell.step())
    return w
def resample(w, e, ph=0.0):
    """receiver clock is faster by factor (1+e): it sees the waveform stretched; ph = sampling phase in units"""
    n=int(len(w)*(1+e)); return [w[min(len(w)-1,int((k+ph)/(1+e)))] for k in range(n)]
def run_rx(cell, w, second=None):
    got=[]
    for k,x in enumerate(w):
        cell.step(x, 1 if second is None else second[k])
        while cell.fifo: got.append(cell.read())
    return got
def tol(make_rx, w, expect, second=None, lo=-0.4, hi=0.4, step=0.005):
    ok=[]
    e=lo
    while e<=hi+1e-9:
        good=True
        for ph in (0.0,0.25,0.5,0.75):
            rx=make_rx()
            ww=resample(w,e,ph); s2=resample(second,e,ph) if second else None
            g=run_rx(rx,ww,s2)
            if not (g==expect and not rx.STUFF and not rx.OVR): good=False
        if good: ok.append(round(e,4))
        e+=step
    # contiguous range around zero
    if 0.0 not in ok: return None
    a=b=0.0
    while round(a-step,4) in ok: a=round(a-step,4)
    while round(b+step,4) in ok: b=round(b+step,4)
    return a,b
res=[]
# ---------- UART, 16 units per bit ----------
data=[0x4B,0x00,0xFF,0x55,0xA5]
tx=Cell(TXEN=1,B=16,SS=1,LSBF=1,IDLE=1,ENC=0xF0)
w=[o for o,_ in [(1,1)]*20+run_tx(tx,data)]
mk=lambda:Cell(RXEN=1,EDGE=2,ACC=1,STOP=2,A=24,B=16,DEC=0xF0,LSBF=1)
r=run_rx(mk(),w); assert r==data,r
res.append(("UART, 16 units per bit",tol(mk,w,data)))
tx=Cell(TXEN=1,B=130,SS=1,LSBF=1,IDLE=1,ENC=0xF0)
w=[o for o,_ in [(1,1)]*200+run_tx(tx,data,tail=400)]
mk=lambda:Cell(RXEN=1,EDGE=2,ACC=1,STOP=2,A=195,B=130,DEC=0xF0,LSBF=1)
assert run_rx(mk(),w)==data
res.append(("UART, 130 units per bit",tol(mk,w,data)))
# ---------- USB low-speed ----------
def usb(upb):
    pkt=[0x80,0xC3,0x00,0xFF,0xFF,0x7E,0x3F,0xAA,0x01]      # sync, PID, payload with long runs of ones
    tx=Cell(TXEN=1,B=upb,LSBF=1,IDLE=0,ENC=0xA5,LIM=6)
    body=run_tx(tx,pkt,tail=0)
    while body and body[-1]==(0,0) and not tx.busy: break
    dp=[0]*(3*upb)+[o for o,_ in body]; dm=[1]*(3*upb)+[n for _,n in body]
    # trim trailing idle generated after busy ended, then append SE0 (2 bits) and J (idle)
    dp+= [0]*(2*upb)+[0]*(12*upb); dm+= [0]*(2*upb)+[1]*(12*upb)
    mk=lambda:Cell(RXEN=1,EDGE=3,ACC=0,STOP=0,A=upb//2,B=upb,DEC=0xC3,LSBF=1,LIM=6,MEN=1,MATCH=0x80,BLEN=1)
    rx=mk(); g=run_rx(rx,dp,dm)
    assert g==pkt[1:],(upb,[hex(v) for v in g]); assert not rx.STUFF
    stuffed=len(tx.tbits)-8*len(pkt)
    return mk,dp,dm,pkt[1:],stuffed,rx
for upb in (10,20,40):
    mk,dp,dm,exp,st,rx=usb(upb)
    res.append((f"USB low-speed, {upb} units per bit ({st} stuffed bits)",tol(mk,dp,exp,dm)))
# keep-alive reference event: SE0 while idle vs SE0 after a packet
mk,dp,dm,exp,st,rx=usb(10)
ev=[(q) for (t,k,q) in rx.refev]; assert ev==[False],ev      # end of packet: line was not idle
rx=mk(); idle_p=[0]*200+[0]*20+[0]*200; idle_m=[1]*200+[0]*20+[1]*200
run_rx(rx,idle_p,idle_m); assert [q for (_,_,q) in rx.refev]==[True]
# ---------- 10BASE-T Manchester ----------
frame=[0x55]*7+[0xD5]+[0x00,0xFF,0x12,0x34,0xA5,0x5A,0x80,0x01]
def eth(half):
    tx=Cell(TXEN=1,B=half,TWOPH=1,LSBF=1,IDLE=0,ENC=0xC3)
    w=[0]*(4*half)+[o for o,_ in run_tx(tx,frame,tail=10*half)]
    mk=lambda:Cell(RXEN=1,EDGE=3,ACC=1,STOP=1,A=(3*half)//2,B=4*half,DEC=0x0F,LSBF=1,MEN=1,MATCH=0xD5)
    rx=mk(); g=run_rx(rx,w); assert g==frame[8:],[hex(v) for v in g]; assert rx.IDLEF
    return mk,w,frame[8:]
mk,w,exp=eth(6); res.append(("10BASE-T, 12 units per bit (both clock edges)",tol(mk,w,exp)))
mk,w,exp=eth(3); res.append(("10BASE-T, 6 units per bit",tol(mk,w,exp)))
# ---------- WS2812 ----------
px=[0xFF,0x00,0xA5,0x3C]
tx=Cell(TXEN=1,CMP=1,B=75,A=48,C=24,LSBF=0)
w=[0]*100+[o for o,_ in run_tx(tx,px,tail=400)]
mk=lambda:Cell(RXEN=1,EDGE=1,ACC=1,STOP=1,A=36,B=150,DEC=0xF0,LSBF=0)
rx=mk(); assert run_rx(rx,w)==px; assert rx.IDLEF
res.append(("WS2812, 75 units per bit",tol(mk,w,px)))
tx=Cell(TXEN=1,CMP=1,B=19,A=12,C=6,LSBF=0)
w=[0]*30+[o for o,_ in run_tx(tx,px,tail=100)]
mk=lambda:Cell(RXEN=1,EDGE=1,ACC=1,STOP=1,A=9,B=38,DEC=0xF0,LSBF=0)
assert run_rx(mk(),w)==px
res.append(("WS2812, 19 units per bit (15 MHz)",tol(mk,w,px)))
# ---------- SPI master, mode 0, loop-back ----------
c=Cell(TXEN=1,RXEN=1,TWOPH=1,B=4,LSBF=0,ENC=0xF0,DEC=0xF0,EDGE=0,STOP=0)
got=[]; q=[0xA5,0x3C,0x81]; x=0; clk=[]
# receive path in the model is edge-started; emulate the common timer by sampling at leading expiries
for _ in range(400):
    if q and c.TXE: c.write(q.pop(0))
    o,_n=c.step(x); x=o; clk.append(c.clk if c.busy else c.CPOL)
rises=sum(1 for a,b in zip(clk,clk[1:]) if a==0 and b==1)
assert rises==24,rises
print("all functional checks passed\n")
for name,t in res:
    print(f"{name:55s} {'%+.1f %% to %+.1f %%'%(100*t[0],100*t[1]) if t else 'FAIL at 0'}")
