"""FIT decoder with correct developer-field handling. Stdlib only."""
import struct, collections
BASE={0:(1,'B',0xFF),1:(1,'b',0x7F),2:(1,'B',0xFF),3:(2,'h',0x7FFF),4:(2,'H',0xFFFF),
 5:(4,'i',0x7FFFFFFF),6:(4,'I',0xFFFFFFFF),7:(1,'s',0x00),8:(4,'f',None),9:(8,'d',None),
 10:(1,'B',0x00),11:(2,'H',0x00),12:(4,'I',0x00),13:(1,'B',0xFF),14:(8,'q',0x7FFFFFFFFFFFFFFF),
 15:(8,'Q',0xFFFFFFFFFFFFFFFF),16:(8,'Q',0x00)}
FIT_EPOCH=631065600
SC=180.0/2**31   # semicircles -> degrees

def _rd(buf,pos,fields,en,devnames):
    rec={}
    for key,sz,bt in fields:
        s,fmt,inv=BASE.get(bt,(1,'B',0xFF)); raw=buf[pos:pos+sz]; pos+=sz
        if bt==7: v=raw.split(b'\x00')[0].decode('utf-8','replace') or None
        elif s>0 and sz==s:
            v=struct.unpack(en+fmt,raw)[0]
            if inv is not None and v==inv: v=None
        elif s>0 and sz%s==0:
            vv=struct.unpack(en+fmt*(sz//s),raw)
            vv=[x for x in vv if inv is None or x!=inv]; v=vv or None
        else: v=raw
        rec[devnames.get(key,key) if isinstance(key,tuple) else key]=v
    return rec,pos

def parse(path):
    buf=open(path,'rb').read(); hsz=buf[0]; dsize=struct.unpack_from('<I',buf,4)[0]
    pos,end=hsz,hsz+dsize; defs={}; msgs=collections.defaultdict(list); devnames={}
    # pass 1 to collect field_description, pass 2 to name them
    for _pass in (1,2):
        pos=hsz; defs={}; msgs=collections.defaultdict(list)
        while pos<end:
            h=buf[pos]; pos+=1
            if h&0x80:
                lmt=(h>>5)&0x03
                if lmt not in defs: break
                g,f,en=defs[lmt]; r,pos=_rd(buf,pos,f,en,devnames); msgs[g].append(r); continue
            lmt=h&0x0F
            if h&0x40:
                pos+=1; en='<' if buf[pos]==0 else '>'; pos+=1
                g=struct.unpack_from(en+'H',buf,pos)[0]; pos+=2
                nf=buf[pos]; pos+=1; fields=[]
                for _ in range(nf):
                    fields.append((buf[pos],buf[pos+1],buf[pos+2]&0x1F)); pos+=3
                if h&0x20:
                    nd=buf[pos]; pos+=1
                    for _ in range(nd):
                        fnum,sz,didx=buf[pos],buf[pos+1],buf[pos+2]; pos+=3
                        bt=devbt.get((didx,fnum),13) if _pass==2 else 13
                        fields.append(((didx,fnum),sz,bt))
                defs[lmt]=(g,fields,en)
            else:
                if lmt not in defs: break
                g,f,en=defs[lmt]; r,pos=_rd(buf,pos,f,en,devnames); msgs[g].append(r)
        if _pass==1:
            devbt={}; devnames={}
            for d in msgs.get(206,[]):
                k=(d.get(0),d.get(1)); devbt[k]=(d.get(2) or 13)&0x1F; devnames[k]=d.get(3)
    return msgs


# ---------------------------------------------------------------------------
# SPIKE, not production code.
#
# This is the throwaway decoder used to answer "what is actually in the FIT?"
# before committing to an architecture. Its findings are written up in
# docs/data-findings.md. Phase 1 replaces it with a real parser in
# api/src/surf/ingest/ that has Pydantic contracts, a full field profile and
# golden tests. Do not import this from application code.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from collections import Counter

    msgs = parse(sys.argv[1])
    for gnum, rows in sorted(msgs.items(), key=lambda kv: -len(kv[1])):
        print(f"msg {gnum:>4}  n={len(rows)}")
    records = msgs[20]
    present = Counter()
    for r in records:
        for k, v in r.items():
            if v is not None:
                present[k] += 1
    print(f"\nrecords={len(records)}")
    for k, c in sorted(present.items(), key=lambda kv: str(kv[0])):
        print(f"  {str(k):>16}: {c}/{len(records)} ({c / len(records) * 100:.1f}%)")
