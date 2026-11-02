"""Small AHK built-ins and script helpers whose exact output matters
(number formats, colours, CRCs written into the INI)."""
import math, re, zlib

_NUM = re.compile(r'\s*[-+]?(0[xX][0-9a-fA-F]+|(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)\s*')


def is_number(v):
    """AHK IsNumber: a number, or a string that is one (decimal, float, 0x hex)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_NUM.fullmatch(v))


def to_num(v):
    """AHK v + 0 on a numeric string."""
    if isinstance(v, (int, float)):
        return v
    s = v.strip()
    if re.fullmatch(r'[-+]?0[xX][0-9a-fA-F]+', s):
        return int(s, 16)
    if re.fullmatch(r'[-+]?\d+', s):
        return int(s)
    return float(s)


def round_ahk(x, n=0):
    """AHK Round(): half away from zero."""
    if n:
        f = 10 ** n
        return math.floor(abs(x) * f + 0.5) / f * (1 if x >= 0 else -1)
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def ahk_str(v):
    """A number as AHK prints it when concatenated (integers bare, floats shortest)."""
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, float):
        return repr(v) if v != int(v) or abs(v) >= 1e15 else repr(v)
    return str(v)


def first_num(s, fallback=0):
    """FirstNum: the leading number of s, else fallback."""
    m = re.match(r'^[+-]?\d+(?:\.\d+)?', str(s).strip(' \t\r\n'))
    return to_num(m.group(0)) if m else fallback


def fmt4(v):
    """Fmt4: four decimals, trailing zeros and point dropped."""
    return ('%.4f' % float(v)).rstrip('0').rstrip('.')


def cap_hex(c, default='#B3B3B3'):
    m = re.fullmatch(r'#?([0-9A-Fa-f]{6})', c or '')
    return '#' + m.group(1).upper() if m else default


def cap_opt_num(v, lo, hi):
    """CapOptNum: v clamped and Fmt4'd, '' when it is no number."""
    v = str(v).strip()
    return fmt4(max(lo, min(hi, to_num(v)))) if is_number(v) else ''


def cap_opt_colour(v):
    v = str(v).strip()
    return cap_hex(v) if re.fullmatch(r'#?[0-9A-Fa-f]{6}', v) else ''


def same_num(a, b):
    return is_number(a) and is_number(b) and to_num(a) == to_num(b)


def sfx_clean(v):
    v = re.sub(r'[\\/:*?"<>|]', '', v.strip())
    return v.strip(' ._')


def crc32_hex(s):
    """Crc32Hex: RtlComputeCrc32 over the string's UTF-16LE bytes."""
    return '%08X' % (zlib.crc32(s.encode('utf-16-le')) & 0xFFFFFFFF)


def ahk_sorted(keys):
    """AHK v2 Map enumeration order: numbers ascending, then strings (case-sensitive, ordinal
    by UTF-16 code unit)."""
    def k(x):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return (0, x, '')
        return (1, 0, str(x).encode('utf-16-be'))
    return sorted(keys, key=k)


def layer_spec_norm(spec):
    out = [t for t in re.sub(r'[\s;]+', ',', spec.strip()).split(',') if re.fullmatch(r'\d{1,3}(-\d{1,3})?', t)]
    return ','.join(out)


def layer_spec_parse(spec):
    out = set()
    for t in re.sub(r'[\s;]+', ',', spec.strip()).split(','):
        if re.fullmatch(r'\d{1,3}', t):
            out.add(int(t))
        else:
            m = re.fullmatch(r'(\d{1,3})-(\d{1,3})', t)
            if m:
                a, b = sorted((int(m.group(1)), int(m.group(2))))
                out.update(range(a, b + 1))
    return out


def pairs_decode(txt):
    return re.sub(r'(?i)\{U\+([0-9A-F]{2,6})\}', lambda m: chr(int(m.group(1), 16)), txt)


def parse_cp_list(s):
    out = set()
    for tok in (s or '').split(','):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r'(?i)u\+?([0-9a-f]{2,6})', tok)
        if m:
            out.add(int(m.group(1), 16))
        else:
            out.update(ord(ch) for ch in tok)
    return out


def anchor_col(v):
    v = str(v).strip()
    m = re.fullmatch(r'(?i)C(\d+)R\d+', v)
    if m:
        v = m.group(1)
    n = first_num(v, 3)
    return n if 3 <= n <= 6 else 3
