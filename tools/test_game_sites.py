"""tools/game_sites.py without game files: the lists agree, and patterns find made-up code wherever it moves.

- VERSIONS == runtime/game_versions.h (the configuration screen's list), the runtime's sites (runtime/game_sites.h)
  and tools/patches.py's are all in SITES, and every supported version's KNOWN table lists every site;
- patterns: the masks keep an instruction's own bits and drop what moves (branch offsets, ADRP pages, the low 12
  bits an ADD / LDR / STR adds to a page in the pattern); the same code at another address, with other targets, is
  found again, and code / call / ref / got / data / end give the right addresses;
- resolve(): a known build's table is the self-check (another address is an error) and the fallback (a pattern that
  finds nothing or several places), a new build needs every pattern to find one place.

Usage: test_game_sites.py
"""
import os
import re
import struct
import sys
from types import SimpleNamespace

import game_sites as gs
import patches

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = gs.MAIN_BASE
checks = 0


def check(cond, what):
    global checks
    if not cond:
        sys.exit(f'FAIL: {what}')
    checks += 1


# ---- instructions (made up, not the game's)
def adrp(rd, pc, to):
    imm = ((to & ~0xFFF) - (pc & ~0xFFF)) >> 12
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | rd


def add_lo12(rd, rn, to): return 0x91000000 | ((to & 0xFFF) << 10) | (rn << 5) | rd
def ldr_x(rt, rn, off): return 0xF9400000 | ((off >> 3) << 10) | (rn << 5) | rt  # ldr xt, [xn, #off]
def ldr_s(rt, rn, off): return 0xBD400000 | ((off >> 2) << 10) | (rn << 5) | rt  # ldr st, [xn, #off]
def str_w(rt, rn, off): return 0xB9000000 | ((off >> 2) << 10) | (rn << 5) | rt  # str wt, [xn, #off]
def bl(pc, to): return 0x94000000 | (((to - pc) >> 2) & 0x3FFFFFF)
def cbz(rt, pc, to): return 0xB4000000 | ((((to - pc) >> 2) & 0x7FFFF) << 5) | rt


NOP, RET = 0xD503201F, 0xD65F03C0
STP, MOV_FP = 0xA9BF7BFD, 0x910003FD  # stp x29, x30, [sp, #-0x10]! / mov x29, sp
LDP = 0xA8C17BFD


def body(pc, data, got, callee):
    """A made-up function at pc: (words, {what: (instruction offset, kind, expected address)})"""
    w = [STP, MOV_FP,
         adrp(8, pc + 8, data), add_lo12(8, 8, data),        # x8 = data
         str_w(9, 8, 0x10),                                   # (a struct offset: kept)
         bl(pc + 20, callee),
         adrp(10, pc + 24, got), ldr_x(10, 10, got & 0xFFF),  # x10 = [got]
         ldr_s(0, 10, 0),
         cbz(0, pc + 36, pc + 48),
         0x52800541,  # mov w1, #42
         LDP, RET]
    return w, {'code': (0, 'code', pc), 'call': (5, 'call', callee), 'ref': (3, 'ref', data),
               'page': (2, 'ref', data & ~0xFFF), 'got': (7, 'got', None)}


def image(fn_at, data, got, callee, got_value, filler=0x40):
    """An NSO-like main module: .text (filler, the function, filler), .data holding the GOT entry"""
    text_size = 0x1000
    words = [NOP] * (text_size // 4)
    fw, sites = body(BASE + fn_at, data, got, callee)
    words[fn_at // 4:fn_at // 4 + len(fw)] = fw
    for i in range(filler // 4):  # (something else that looks a bit alike: the pattern must not stop there)
        words[i] = STP if i % 7 == 0 else MOV_FP if i % 7 == 1 else NOP
    data_off, size = 0x2000, 0x4000
    img = bytearray(size)
    struct.pack_into(f'<{len(words)}I', img, 0, *words)
    struct.pack_into('<Q', img, got - BASE, got_value)  # (module-relative, as before relocation)
    nso = SimpleNamespace(image=bytes(img), text=(0, text_size), data=(data_off, 0x1000), size=size,
                          build_id='00' * 16)
    return gs.Main(nso), sites


def main():
    # ---- the lists agree
    h = open(os.path.join(ROOT, 'runtime', 'game_versions.h'), encoding='utf-8').read()
    hv = re.findall(r'X\("([^"]*)", "([0-9a-f]*)", ([01]), \d+, "([0-9a-f]*)", ([01])\)', h)  # (the RomFS file count
    check(hv == [(v.name, v.build_id, str(int(v.supported)), v.title_id, str(int(v.generic))) for v in gs.VERSIONS],
          f'runtime/game_versions.h {hv} == game_sites.VERSIONS')  # is the setup's alone)
    for v in gs.VERSIONS:  # (a version with no build id is told by its title id; one with a build id by that)
        check(v.build_id or v.title_id, f'{v.name}: has a build id or a title id')
        check(not v.title_id or re.fullmatch(r'[0-9a-f]{16}', v.title_id), f'{v.name}: title id is 16 lowercase hex digits')
    names = {s.name for s in gs.SITES}
    check(len(names) == len(gs.SITES), 'site names are unique')
    rt = re.findall(r'X\((\w+)\)', open(os.path.join(ROOT, 'runtime', 'game_sites.h'), encoding='utf-8').read())
    check(rt and set(rt) <= names, f'the runtime\'s sites are in SITES: {set(rt) - names}')
    check(set(patches.PATCHES) <= names, f'tools/patches.py\'s sites are in SITES: {set(patches.PATCHES) - names}')
    for v in gs.VERSIONS:
        if v.supported and not v.generic:  # (a generic game has no sites: nothing to list)
            check(set(gs.KNOWN.get(v.name, {})) == names, f'{v.name}: KNOWN lists every site')
        if v.generic:
            check(v.name not in gs.KNOWN, f'{v.name}: a generic game has no KNOWN table')
    check(all(gs.compile_pattern(p) for s in gs.SITES if s.pattern
              for p in ([q for q, _ in s.pattern] if isinstance(s.pattern, list) else [s.pattern])),
          'every pattern compiles')

    # ---- masks
    check(gs.make_pattern([bl(0x1000, 0x5000)]) == '94000000/fc000000', 'bl: only the opcode')
    check(gs.make_pattern([adrp(3, 0x1000, 0x123456000), add_lo12(3, 3, 0x123456789), ldr_x(4, 3, 0x18)]) ==
          '90000003/9f00001f 91000063/ffc003ff f9400c64', 'adrp + add: page and low bits masked; then a struct offset')
    check(gs.make_pattern([ldr_x(4, 3, 0x18)]) == 'f9400c64', 'ldr without an adrp in the pattern: kept')
    check(gs.make_pattern([cbz(1, 0, 0x40)]) == 'b4000001/ff00001f', 'cbz: register kept, offset masked')

    # ---- the same code elsewhere, with other targets
    a, sa = image(0x400, 0x7000002468, 0x7000002a10, 0x7000000040, 0x3abc)
    b, sb = image(0x800, 0x7000002f30, 0x7000002b08, 0x7000000100, 0x3ff0)
    pat = gs.make_pattern(a.text_words(BASE + 0x400, 13))
    check(gs.make_pattern(b.text_words(BASE + 0x800, 13)) == pat, 'moved code: the same pattern')
    for m, s, at in ((a, sa, 0x400), (b, sb, 0x800)):
        check(m.find(pat) == [BASE + at], f'found at {at:#x} only ({[hex(x) for x in m.find(pat)]})')
        for what, (k, kind, want) in s.items():
            got = m.target(kind, BASE + at + 4 * k)
            if kind == 'got':
                want = BASE + struct.unpack_from('<Q', m.nso.image, (0x2a10 if m is a else 0x2b08))[0]
            check(got == want, f'{what} at {at:#x}: {got:#x} (want {want:#x})')
    found, n = b.locate(gs.Site('x', 'data', '', 0))
    check((found, n) == (BASE + 0x2000, 1), 'data: where .data starts')
    check(b.locate(gs.Site('x', 'end', '', 0))[0] == BASE + 0x4000, 'end: where the image ends')
    a.fdes = []  # (no unwind info: a window around the instruction)
    p, back = a.pattern_for(BASE + 0x400 + 4 * 7, 'got')
    check(back >= 1 and a.find(p) == [BASE + 0x400 + 4 * 7 - 4 * back], 'pattern_for: starts at its ADRP or above')

    # ---- resolve(): the table checks and falls back
    sites = [gs.Site('fn', 'code', pat, 0), gs.Site('callee', 'call', pat, 5), gs.Site('data', 'ref', pat, 3)]
    saved = gs.SITES
    try:
        gs.SITES = sites
        r = gs.resolve(b)
        check(r == {'fn': BASE + 0x800, 'callee': 0x7000000100, 'data': 0x7000002f30}, f'new build by pattern: {r}')
        try:
            gs.resolve(b, {'fn': BASE + 0x804})
            check(False, 'a table that disagrees with the pattern is refused')
        except gs.SiteError:
            check(True, '')
        gs.SITES = [gs.Site('fn', 'call', [('d503201f 12345678', 0), (pat, 5)], 0)]  # (a version's own pattern)
        check(gs.resolve(b) == {'fn': 0x7000000100}, 'a list of patterns: the first that finds one place')
        gs.SITES = [gs.Site('fn', 'code', 'd503201f d503201f', 0)]  # (several places)
        logs = []
        check(gs.resolve(b, {'fn': BASE + 0x800}, logs.append) == {'fn': BASE + 0x800} and logs,
              'several places: the table, with a warning')
        try:
            gs.resolve(b)
            check(False, 'several places and no table: refused')
        except gs.SiteError as e:
            check('matches 2 places or more' in str(e), str(e))
    finally:
        gs.SITES = saved

    # ---- versions
    check(gs.supported_version('de0b6ac4efc1dda7f80f6d7598ec7a7d' + '0' * 32).name == '1.8.2', '1.8.2 by build id')
    check(gs.supported_version('ff' * 32) is None, 'an unknown build')
    try:
        gs.for_module(b.nso, BASE)
        check(False, 'an unknown main module is refused')
    except gs.SiteError as e:
        check('not a version Savage Wind knows' in str(e), str(e))

    # ---- a generic game (Xenoblade Chronicles 3), told by the title id of its main.npdm
    xc3 = 'XC3 1.0.0'
    tid = '010074f013262000'
    unknown = 'ab' * 32  # (a main build id no version lists)
    check(gs.supported_version(unknown, tid) and gs.supported_version(unknown, tid).name == xc3, 'XC3 by its title id')
    check(gs.supported_version(unknown, tid.upper()).name == xc3, 'the title id is compared without case')
    check(gs.supported_version(unknown, '01007ef00011e000') is None, 'another title id: not known')
    check(gs.supported_version(unknown, None) is None and gs.supported_version(unknown) is None, 'no npdm: not known')
    check(gs.supported_version('de0b6ac4efc1dda7' + '0' * 48, tid).name == '1.8.2', 'a build id wins over a title id')
    logs = []
    fake = SimpleNamespace(build_id=unknown, image=b'', text=(0, 0), data=(0, 0), size=0)
    check(gs.for_module(fake, BASE, False, logs.append, tid) == (xc3, {}) and logs, 'generic: no sites, and it says so')
    try:
        gs.for_module(fake, BASE)  # (the same main module without its npdm)
        check(False, 'a main module that only the title id knows needs the npdm')
    except gs.SiteError as e:
        check('not a version Savage Wind knows' in str(e), str(e))
    try:
        gs.for_module(fake, BASE, False, None, '0100000000000000')
        check(False, 'another title id is refused')
    except gs.SiteError as e:
        check('title id 0100000000000000' in str(e), str(e))

    # ---- program_id(): main.npdm as boot() in runtime/main.c reads it
    from nso import program_id
    import tempfile

    def npdm(pid, aci=0x80, magic=b'META', aci_magic=b'ACI0', size=0x200):
        raw = bytearray(size)
        raw[:4] = magic
        struct.pack_into('<I', raw, 0x70, aci)
        raw[aci:aci + 4] = aci_magic
        if aci + 0x18 <= size:  # (else the file ends inside the ACI0 header, which is what that case tests)
            struct.pack_into('<Q', raw, aci + 0x10, pid)
        return bytes(raw)

    with tempfile.TemporaryDirectory() as d:
        def pid_of(data):
            p = os.path.join(d, 'main.npdm')
            with open(p, 'wb') as f:
                f.write(data)
            return program_id(p)
        check(pid_of(npdm(0x010074F013262000)) == tid, 'program_id: XC3\'s')
        check(pid_of(npdm(0x01007EF00011E000)) == '01007ef00011e000', 'program_id: BOTW\'s')
        check(pid_of(npdm(0x1, aci=0x100)) == '0000000000000001', 'program_id: padded to 16 digits, ACI0 elsewhere')
        check(pid_of(npdm(1, magic=b'XXXX')) is None, 'program_id: not a META file')
        check(pid_of(npdm(1, aci_magic=b'XXXX')) is None, 'program_id: no ACI0')
        check(pid_of(npdm(1, aci=0x1f0)) is None, 'program_id: ACI0 past the end')
        check(pid_of(b'META') is None, 'program_id: too short')
        check(program_id(os.path.join(d, 'nothing.npdm')) is None, 'program_id: no file')
    print(f'ok: {checks} checks')


if __name__ == '__main__':
    main()
