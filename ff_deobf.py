import sys
import os
import re
import json
import gzip
import difflib

current = os.path.dirname(os.path.abspath(__file__))
ref = os.path.join(current, "ref.bin")
DEFAULT_OUTPUT = "dumped_full.cs"

transport = {
    "UDPMsgPacket", "UDPMsgPacketResendInfo", "UDPMsgPacketTrackingData",
    "UDPReliableTracking", "UDPSession", "MUDPSession", "TCPMsgPacket",
    "UDPClientMessageBase", "UDPMessagePool", "NetworkSession",
}

datas = {
    "uint": "U32", "UInt32": "U32", "int": "I32", "Int32": "I32",
    "ushort": "U16", "UInt16": "U16", "short": "I16", "Int16": "I16",
    "ulong": "U64", "UInt64": "U64", "long": "I64", "Int64": "I64",
    "byte": "U8", "Byte": "U8", "sbyte": "I8", "SByte": "I8",
    "bool": "BOOL", "Boolean": "BOOL", "float": "F32", "Single": "F32",
    "double": "F64", "Double": "F64", "string": "STR", "String": "STR",
    "char": "CHAR", "Char": "CHAR",
}

class_line = re.compile(r"\bclass\s+([A-Za-z_]\w*)")
msgbase = re.compile(r":\s*UDPClientMessageBase\b")
fieldsre = re.compile(r"^\s*public\s+(\S+)\s+(\w+)\s*;")


def norm(type_name):
    if "List`" in type_name or "List<" in type_name:
        return "LIST"
    if type_name in datas:
        return datas[type_name]
    if type_name.endswith("[]"):
        return "ARR"
    return "OBJ"


def normkey(name):
    name = re.sub(r"^(C2S_|S2C_|MUDP_|RUDP_|RUPD_|UDP_)+", "", name)
    name = re.sub(r"(_Req|_Res|_Ack|_Ntf|_Notify)$", "", name)
    return name.replace("_", "").upper()


def load_ref():
    if not os.path.isfile(ref):
        sys.exit(f"[!] ref data not found next to the script: {ref}")
    with gzip.open(ref, "rb") as f:
        data = json.loads(f.read())
    order = [(name, tuple(sig.split(",")) if sig else ()) for name, sig in data["order"]]
    name_to_id = data["n2i"]
    id_to_name = {int(k): v for k, v in data["i2n"].items()}
    fields = data["fields"]
    return order, name_to_id, id_to_name, fields


def parse(path):
    classes = []
    cur = None
    section = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            text = line.rstrip("\n")
            match = class_line.search(line)
            if match:
                name = match.group(1)
                kind = None
                if name in transport:
                    kind = "transport"
                elif msgbase.search(line):
                    kind = "msg"
                if kind:
                    if cur is not None:
                        classes.append(cur)
                    cur = {"name": name, "kind": kind, "flds": [], "raw": [text]}
                    section = "pre"
                    continue
                if cur is not None:
                    classes.append(cur)
                    cur = None
                    section = None
                continue
            if cur is None:
                continue
            cur["raw"].append(text)
            raw_index = len(cur["raw"]) - 1
            if "// Properties" in line or "// Methods" in line:
                section = "rest"
                continue
            if line.startswith("}"):
                classes.append(cur)
                cur = None
                section = None
                continue
            if section in ("pre", "fields"):
                fm = fieldsre.match(line)
                if fm:
                    section = "fields"
                    cur["flds"].append((norm(fm.group(1)), fm.group(2), raw_index))
        if cur is not None:
            classes.append(cur)
    for c in classes:
        c["sig"] = tuple(t for t, _, _ in c["flds"])
    return classes


def common_prefix(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def align_field_names(inp_flds, ref_flds):
    inp_types = [t for t, _, _ in inp_flds]
    ref_types = [t for t, _ in ref_flds]
    sm = difflib.SequenceMatcher(None, ref_types, inp_types, autojunk=False)
    out = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                real = ref_flds[i1 + k][1]
                _, obf, raw_index = inp_flds[j1 + k]
                if real and real != obf:
                    out[raw_index] = (obf, real)
    return out


def assign_names(ref_order, msg_sigs):
    ref_sigs = [sig for _, sig in ref_order]
    sm = difflib.SequenceMatcher(None, ref_sigs, msg_sigs, autojunk=False)
    assigned = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                assigned[j1 + k] = (ref_order[i1 + k][0], "exact")
        elif tag == "replace":
            block = list(range(i1, i2))
            used = set()
            for jj in range(j1, j2):
                sig = msg_sigs[jj]
                best = None
                for ii in block:
                    if ii in used:
                        continue
                    score = common_prefix(sig, ref_order[ii][1]) + common_suffix(sig, ref_order[ii][1])
                    if best is None or score > best[0]:
                        best = (score, ii)
                if best and best[0] > 0:
                    used.add(best[1])
                    assigned[jj] = (ref_order[best[1]][0], "near")
    return assigned


def parse_args(argv):
    flag = next((i for i, a in enumerate(argv) if a in ("-o", "--output")), None)
    if flag is None:
        inp_tokens, out_tokens = argv, []
    else:
        inp_tokens, out_tokens = argv[:flag], argv[flag + 1:]

    def clean(tokens):
        return " ".join(tokens).strip().strip('"').strip("'")

    return clean(inp_tokens), (clean(out_tokens) or None)


def resolve_output(out_name):
    if not out_name:
        return DEFAULT_OUTPUT
    if os.path.splitext(out_name)[1] == "":
        out_name += ".cs"
    return out_name


def main():
    inp, out_name = parse_args(sys.argv[1:])
    if not inp:
        inp = input("Path to the OBFUSCATED dump: ").strip().strip('"')
    if not os.path.isfile(inp):
        sys.exit(f"[!] not found: {inp}")
    output = resolve_output(out_name)

    ref_order, name_to_id, id_to_name, ref_fields = load_ref()
    classes = parse(inp)

    msg_pos = [i for i, c in enumerate(classes) if c["kind"] == "msg"]
    transport_n = sum(1 for c in classes if c["kind"] == "transport")
    print(f"[*] message classes: {len(msg_pos)}   transport classes: {transport_n}   ref: {len(ref_order)}")

    msg_sigs = [classes[i]["sig"] for i in msg_pos]
    assigned = assign_names(ref_order, msg_sigs)

    real_for = {msg_pos[pos]: val for pos, val in assigned.items()}
    obf2real = {classes[msg_pos[pos]]["name"]: real for pos, (real, _) in assigned.items()}

    def fix_types(line):
        return re.sub(r"message\.(\w+)",
                      lambda m: obf2real.get(m.group(1), "message." + m.group(1)),
                      line)

    exact = sum(1 for v in assigned.values() if v[1] == "exact")
    near = sum(1 for v in assigned.values() if v[1] == "near")
    new = len(msg_pos) - len(assigned)
    renamed_fields = 0

    with open(output, "w", encoding="utf-8") as out:
        out.write(f"// de-obfuscated from (obfuscated) {os.path.basename(inp)}\n")
        out.write(f"// messages: exact={exact} near={near} new={new}   transport classes: {transport_n}\n")
        out.write("// full bodies verbatim; class + field names restored wcurrent aligned\n\n")

        for idx, c in enumerate(classes):
            realname = None
            if c["kind"] == "transport":
                out.write(f"// [transport] {c['name']}\n")
                name = c["name"]
                realname = c["name"]
            elif idx in real_for:
                real, conf = real_for[idx]
                msgid = name_to_id.get(normkey(real))
                if msgid is not None:
                    out.write(f"// msgid {msgid}  {id_to_name.get(msgid, '')}\n")
                out.write(f"// [{conf}] obf={c['name']}\n")
                name = real
                realname = real
            else:
                out.write(f"// [new] obf={c['name']}\n")
                name = c["name"]

            raw = list(c["raw"])
            raw[0] = re.sub(r"(\bclass\s+)" + re.escape(c["name"]) + r"\b",
                            lambda mm: mm.group(1) + name, raw[0])

            if realname and realname in ref_fields:
                for raw_index, (obf, real) in align_field_names(c["flds"], ref_fields[realname]).items():
                    raw[raw_index] = re.sub(r"\b" + re.escape(obf) + r"\s*;", real + ";", raw[raw_index], count=1)
                    if "//" in raw[raw_index]:
                        raw[raw_index] = raw[raw_index].rstrip() + " OBF : " + obf
                    else:
                        raw[raw_index] = raw[raw_index].rstrip() + " // OBF : " + obf
                    renamed_fields += 1

            for line in raw:
                out.write(fix_types(line) + "\n")
            out.write("\n")

    print(f"[+] wrote {os.path.abspath(output)}")
    print(f"    messagess: exact={exact} near={near} new={new}   transport={transport_n}   fields renamed={renamed_fields}")


if __name__ == "__main__":
    main()
