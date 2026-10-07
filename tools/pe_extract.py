import sys, pefile
exe, outdir = sys.argv[1], sys.argv[2]
pe = pefile.PE(exe)
for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
    if str(t.name) != "FIRMWARE":
        continue
    for r in t.directory.entries:
        for l in r.directory.entries:
            d = l.data.struct
            data = pe.get_data(d.OffsetToData, d.Size)
            p = f"{outdir}/fw_{r.id}.bin"
            open(p, "wb").write(data)
            print("written:", p, len(data), "bytes")
