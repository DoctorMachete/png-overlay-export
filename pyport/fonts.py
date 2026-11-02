"""Font fallback of the .148 script: LoadProbeCache, CpNeedsFallback,
CharsNeedingFallback, FontFixStyle, EmojiSpans, NormaliseFonts, IsEmojiCp,
IsIgnorableCp, FontCoversCp.  (ProbeGlyphs, which measures new characters by
rendering test pages, is not ported yet: characters missing from
font_probe.txt fall back to the font coverage test, as the script does.)

FontCoversCp asks Windows GDI on Windows; elsewhere it reads the font file
given by FONT_FILES (or assumes covered, as the script does when GDI fails)."""
import os, re, sys
import model as M

PROBE_SCHEMA = 4
FONT_FILES = {}          # family -> .ttf path, for the coverage test off Windows

_EMOJI = [(0x1F300, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF), (0x1FA70, 0x1FAFF),
          (0x1F004, 0x1F004), (0x1F0CF, 0x1F0CF), (0x1F170, 0x1F171), (0x1F17E, 0x1F17F),
          (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1E6, 0x1F1FF), (0x1F201, 0x1F202),
          (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F), (0x1F232, 0x1F23A), (0x1F250, 0x1F251),
          (0x1F7E0, 0x1F7EB), (0x1F7F0, 0x1F7F0)]


def is_emoji_cp(cp):
    return 0x1F000 <= cp <= 0x1FAFF and any(a <= cp <= b for a, b in _EMOJI)


def is_ignorable_cp(cp):
    return 0x200B <= cp <= 0x200F or 0x2060 <= cp <= 0x2064 or 0xFE00 <= cp <= 0xFE0F or cp == 0xFEFF


class Fonts:
    def __init__(self, cfg):
        self.cfg = cfg
        self.probe, self.probe_fix, self.dead = {}, {}, False
        self.cache = {}
        self.load_probe_cache(os.path.join(cfg.base_dir, 'font_probe.txt'))

    def fix_family(self):
        return self.cfg.font_over

    def load_probe_cache(self, path):
        if not os.path.isfile(path):
            return
        txt = open(path, encoding='utf-8-sig').read()
        lines = [l.strip() for l in txt.splitlines()]
        if f'schema={PROBE_SCHEMA}' not in lines or f'stack={self.fix_family()}' not in lines:
            return
        for line in lines:
            if line == 'hexboxes=1':
                self.dead = True
                continue
            p = line.split('|')
            if len(p) < 4 or p[0] != self.cfg.font_base:
                continue
            cp = int(p[1], 16)
            self.probe[cp] = p[2] == 'box'
            self.probe_fix[cp] = p[3] == 'box'

    def covers(self, family, cp):
        """FontCoversCp."""
        if cp <= 0x7E or is_ignorable_cp(cp):
            return True
        key = (family, cp)
        if key in self.cache:
            return self.cache[key]
        ok = True
        if cp <= 0xFFFF:
            ok = _covers(family, cp)
        self.cache[key] = ok
        return ok

    def needs_fallback(self, cp):
        """CpNeedsFallback."""
        c = self.cfg
        if cp <= 0x7E or is_ignorable_cp(cp) or cp in c.keep_chars:
            return False
        if cp in c.fix_chars:
            return True
        if cp in self.probe:
            return self.probe[cp]
        if cp > 0xFFFF:
            return not is_emoji_cp(cp)
        return not self.covers(c.font_base, cp)

    def chars_needing_fallback(self, txt):
        miss, seen = [], set()
        for ch in txt:
            cp = ord(ch)
            if cp > 0x7E and cp not in seen:
                seen.add(cp)
                if self.needs_fallback(cp):
                    miss.append(ch)
        return ''.join(miss)

    def font_fix_style(self, st, txt):
        """FontFixStyle: the style with the right fontFamily, or '' when unchanged."""
        c = self.cfg
        if not st or c.font_over == '' or c.font_mode == 'off':
            return ''
        has = 'fontfamily=' in st.lower()          # AHK InStr ignores case
        if c.font_mode == 'all':
            want = c.font_over
            if not has and st.startswith('group;'):
                return ''
        elif self.chars_needing_fallback(txt) != '':
            want = self.fix_family()
        elif has:
            want = c.font_base
        else:
            return ''
        if has:
            new = re.sub(r'(?i)fontFamily=[^;]*', lambda m: 'fontFamily=' + want, st)
        else:
            new = st.rstrip(';') + ';fontFamily=' + want + ';'
        return '' if new == st else new

    @staticmethod
    def emoji_spans(v):
        out, run = [], ''
        span = '<span style="font-family: \'Segoe UI Emoji\'">'
        for ch in v:
            cp = ord(ch)
            if is_emoji_cp(cp) or (run and (cp in (0x200D, 0xFE0F, 0x20E3) or 0xE0020 <= cp <= 0xE007F)):
                run += ch
            else:
                if run:
                    out.append(span + run + '</span>')
                    run = ''
                out.append(ch)
        if run:
            out.append(span + run + '</span>')
        return ''.join(out)

    def normalise(self, doc_root, skip_ids=()):
        """NormaliseFonts over a page."""
        if self.cfg.font_over == '':
            return
        for c in doc_root.xpath('//mxCell[@style]'):
            if c.get('id') in skip_ids:
                continue
            new = self.font_fix_style(c.get('style'), M.plain_text(c))
            if new:
                c.set('style', new)
            cst = c.get('style')
            if M.style_get(cst, 'html', '') == '1' and M.style_get(cst, 'fontFamily', '') == self.fix_family():
                v = c.get('value') or ''
                if v:
                    nv = self.emoji_spans(v)
                    if nv != v:
                        c.set('value', nv)
        for c in doc_root.xpath('//mxCell[@value]'):
            if c.get('id') in skip_ids:
                continue
            v = c.get('value')
            if v and 'u2000' in v.lower():
                c.set('value', re.sub(r'(?i)font-family:\s*u2000', 'font-family:inherit', v))


NOT_COVERED = {}         # family -> set of code points: a stand-in for GDI off Windows (tests)


def _covers(family, cp):
    """FontCoversCp's question to Windows: does the font GDI picks for family (Helvetica ->
    Arial, by FontSubstitutes) have a glyph for cp?"""
    if family in NOT_COVERED:
        return cp not in NOT_COVERED[family]
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes
            gdi, user = ctypes.WinDLL('gdi32'), ctypes.WinDLL('user32')
            user.GetDC.restype = wintypes.HDC
            user.GetDC.argtypes = [wintypes.HWND]
            user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
            gdi.CreateFontW.restype = wintypes.HFONT
            gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
            gdi.SelectObject.restype = wintypes.HGDIOBJ
            gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
            gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            gdi.GetGlyphIndicesW.restype = wintypes.DWORD
            gdi.GetGlyphIndicesW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                             ctypes.POINTER(wintypes.WORD), wintypes.DWORD]
            hdc = user.GetDC(None)
            if not hdc:
                return True
            ok = True
            hf = gdi.CreateFontW(-16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, family)
            if hf:
                old = gdi.SelectObject(hdc, hf)
                buf = (wintypes.WORD * 1)()
                r = gdi.GetGlyphIndicesW(hdc, chr(cp), 1, buf, 1)      # GGI_MARK_NONEXISTING_GLYPHS
                if r != 0xFFFFFFFF:
                    ok = buf[0] != 0xFFFF
                gdi.SelectObject(hdc, old)
                gdi.DeleteObject(hf)
            user.ReleaseDC(None, hdc)
            return ok
        except Exception:
            return True
    fp = FONT_FILES.get(family)
    if not fp:
        return True
    try:
        from fontTools.ttLib import TTFont
        if fp not in _cmaps:
            _cmaps[fp] = TTFont(fp, fontNumber=0).getBestCmap()
        return cp in _cmaps[fp]
    except Exception:
        return True


_cmaps = {}
