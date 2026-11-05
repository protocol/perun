import json,os,re
D="/private/tmp/claude-501/heldout-api5-author"
cs=json.load(open(D+"/cases.json"))
ban=re.compile(r"vuln|insecure|unsafe|safe|todo|fixme|exploit|flaw|idor|bola|owasp|api\d|broken|bfla",re.I)
print(sum(c["kind"]=="pos" for c in cs),sum(c["kind"]=="neg" for c in cs),len(cs))
for c in cs:
    d=f"{D}/cases/{c['id']}"
    fs=[os.path.join(r,f) for r,_,x in os.walk(d) for f in x]
    n=sum(len(open(f).read().splitlines()) for f in fs)
    t=[x for f in fs for x in open(f).read().splitlines()]
    if not(1<=len(fs)<=3 and 15<=n<=80): print("SIZE",c["id"],len(fs),n)
    if any(ban.search(l) for l in t) or ban.search(" ".join(os.path.relpath(f,d) for f in fs)): print("BAN",c["id"])
    if c["kind"]=="pos":
        l=open(f"{d}/{c['truth_file']}").read().splitlines()[c["truth_line"]-1]
        if not re.search(r"route|router\.|app\.|admin\.|bp\.",l): print("TRUTH",c["id"],l)
        print(c["id"],l.strip()[:60]) if False else None
    elif c["truth_file"] or c["truth_line"]: print("NEGTRUTH",c["id"])
print("done")
