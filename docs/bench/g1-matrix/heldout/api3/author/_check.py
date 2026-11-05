import json,os,re
B="/private/tmp/claude-501/heldout-api3-author/cases"
cs=json.load(open("/private/tmp/claude-501/heldout-api3-author/cases.json"))
print(len(cs),sum(c["kind"]=="pos" for c in cs),sum(c["kind"]=="neg" for c in cs))
ban=["vuln","insecure","unsafe","safe","todo","fixme","exploit","flaw","idor","bola","owasp"]
for c in cs:
    d=os.path.join(B,c["id"]);fs=[os.path.join(r,f) for r,_,n in os.walk(d) for f in n]
    tot=0
    if not 1<=len(fs)<=3:print("files",c["id"])
    for f in fs:
        t=open(f).read();n=len(t.splitlines());tot+=n
        if n>80 or (len(fs)>1 and n<15):print("lines",f,n)
        tl=t.lower()
        for b in ban:
            if b in tl:print("ban",f,b)
        if re.search(r"api\s*-?\d",tl):print("apilabel",f)
    if tot<15:print("total",c["id"],tot)
    if c["kind"]=="pos":
        l=open(os.path.join(d,c["truth_file"])).read().splitlines()[c["truth_line"]-1];print(c["id"],c["truth_line"],l.strip())
