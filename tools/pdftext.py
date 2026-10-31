import zlib,re,sys
d=open(sys.argv[1],"rb").read()
for m in re.finditer(rb"stream\r?\n(.*?)endstream",d,re.S):
    try: s=zlib.decompress(m.group(1))
    except Exception: continue
    if b"BT" not in s: continue
    out=[]
    for t in re.finditer(rb"\[(.*?)\]\s*TJ|\((.*?)(?<!\\)\)\s*Tj",s,re.S):
        if t.group(1) is not None:
            out.append(b"".join(re.findall(rb"\((.*?)(?<!\\)\)",t.group(1),re.S)))
        else: out.append(t.group(2))
    print("----stream");print(b" | ".join(out).decode("latin1")[:3000])
