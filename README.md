# FF_DEOBF

De-obfuscates Free Fire il2cpp `.cs` dumps: restores the real **class** and
**field** names of every UDP message class and writes them to `dumped_new.cs`,
keeping the input dump's own offsets and full class bodies verbatim.

## Usage

```bash
python ff_deobf.py "path\to\obfuscated_dump.cs"
python ff_deobf.py "path\to\dump.cs" -o redzed.cs
python ff_deobf.py "path\to\dump.cs" -o redzed          # ".cs" added for you
```

- The input path may contain spaces **without quotes**, e.g.
  `python ff_deobf.py C:\Users\RedZed\Downloads\Telegram Desktop\FREE FIRE NORMAL DUMP.CS -o redzed`
- `-o` / `--output` sets the output name; the `.cs` extension is added if you
  leave it off. Without `-o` the output is **`dumped_full.cs`**.
- No argument at all → it prompts for the path.

The output file is written to the folder you run the command from.

## Files

| File            | Purpose                                                       |
| --------------- | ------------------------------------------------------------- |
| `ff_deobf.py`   | The tool.                                                     |
| `ref.bin` | Reference fingerprints + real names (gzip JSON). **Required** — keep it next to `ff_deobf.py`. |

## How names are recovered

There is no name-decrypt key — the obfuscated names are per-build random. Names
are recovered **structurally**:

1. Each class is reduced to a field-type fingerprint (primitives and `List<>`
   survive obfuscation; struct types normalise to `OBJ`).
2. The input dump is aligned against the reference by fingerprint order
   (`difflib`), which resolves even classes that share a fingerprint.
3. Aligned classes take the reference's real name; fields are re-aligned per
   class the same way. The original obfuscated name is kept on each renamed
   field as a trailing `// ... OBF : <name>` comment.

## Output annotations

```
// msgid 1336  RUDP_S2C_Create_PureModelObject
// [exact] obf=BJDELPPGAFE
internal class RUDP_S2C_Create_PureModelObject : UDPClientMessageBase
{
    public uint AttackableEntityID; // 0x14 OBF : NMGDAKFKJLH
    ...
}
```

- `[exact]` layout matches the reference exactly.
- `[near]` layout changed slightly (a field added/removed); best-effort match.
- `[new]` no match in the reference; obfuscated name kept.
- `[transport]` framing class kept by its real (un-obfuscated) name.

### © Desire Team .
<p align="center"><b>For Support, Please Contact ME <a href="https://t.me/redzedking">TELEGRAM</a> - <a href="https://discord.com/users/t3is">DISCORD</a> - <a href="https://www.youtube.com/@redzedking">YOUTUBE</a></b></p>


