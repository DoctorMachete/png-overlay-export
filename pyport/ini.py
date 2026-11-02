"""The INI file, read and written as AHK's IniRead / IniWrite / IniDelete do
(the Windows profile API): section and key names ignore case, values are
trimmed, and a write edits the file in place - the line of an existing key is
replaced, a new key goes after the section's last entry, a new section at the
end.  Every call re-reads the file, so changes AHK makes between calls are
kept.  The encoding (UTF-16 with BOM, UTF-8 with or without BOM) and CRLF line
ends are kept as found."""
import os, re

_SEC = re.compile(r'^\s*\[([^\]]*)\]')


class Ini:
    def __init__(self, path):
        self.path = path

    # ------------------------------------------------------------- file
    def _load(self):
        try:
            b = open(self.path, 'rb').read()
        except FileNotFoundError:
            self._enc, self._bom = 'utf-8', b''
            return []
        if b[:2] == b'\xff\xfe':
            self._enc, self._bom = 'utf-16-le', b'\xff\xfe'
            t = b[2:].decode('utf-16-le')
        elif b[:3] == b'\xef\xbb\xbf':
            self._enc, self._bom = 'utf-8', b'\xef\xbb\xbf'
            t = b[3:].decode('utf-8')
        else:
            self._bom = b''
            try:
                t, self._enc = b.decode('utf-8'), 'utf-8'
            except UnicodeDecodeError:
                t, self._enc = b.decode('cp1252'), 'cp1252'
        lines = t.split('\r\n') if '\r\n' in t else t.split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        return lines

    def _save(self, lines):
        t = ''.join(l + '\r\n' for l in lines)
        tmp = self.path + '.tmp~'
        with open(tmp, 'wb') as f:
            f.write(self._bom + t.encode(self._enc))
        os.replace(tmp, self.path)

    @staticmethod
    def _span(lines, section):
        """(header index, end index) of the first section of that name, or None."""
        s = section.strip().lower()
        start = None
        for i, l in enumerate(lines):
            m = _SEC.match(l)
            if m:
                if start is not None:
                    return start, i
                if m.group(1).strip().lower() == s:
                    start = i
        return (start, len(lines)) if start is not None else None

    @staticmethod
    def _kv(line):
        if '=' not in line:
            return None
        k, v = line.split('=', 1)
        return k.strip(), v

    @staticmethod
    def _val(v):
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        return v

    # ------------------------------------------------------------- reads
    def read(self, section, key, default=''):
        """IniRead(file, section, key, default)."""
        lines = self._load()
        sp = self._span(lines, section)
        if sp:
            kl = key.lower()
            for l in lines[sp[0] + 1:sp[1]]:
                kv = self._kv(l)
                if kv and kv[0].lower() == kl:
                    return self._val(kv[1])
        return default if isinstance(default, str) else str(default)

    def section(self, section):
        """IniRead(file, section): the section's key=value lines, or None when absent."""
        lines = self._load()
        sp = self._span(lines, section)
        if not sp:
            return None
        out = []
        for l in lines[sp[0] + 1:sp[1]]:
            kv = self._kv(l)
            if kv and kv[0] and not kv[0].startswith(';'):
                out.append(kv[0] + '=' + kv[1].strip())
        return '\n'.join(out)

    def sections(self):
        """IniRead(file): every section name."""
        return [m.group(1).strip() for l in self._load() for m in [_SEC.match(l)] if m]

    # ------------------------------------------------------------- writes
    def write(self, value, section, key):
        """IniWrite(value, file, section, key)."""
        value = str(value)
        lines = self._load()
        sp = self._span(lines, section)
        if not sp:
            lines += ['[' + section + ']', key + '=' + value]
        else:
            kl = key.lower()
            for i in range(sp[0] + 1, sp[1]):
                kv = self._kv(lines[i])
                if kv and kv[0].lower() == kl:
                    lines[i] = kv[0] + '=' + value
                    break
            else:
                at = sp[1]
                while at > sp[0] + 1 and lines[at - 1].strip() == '':
                    at -= 1
                lines.insert(at, key + '=' + value)
        self._save(lines)

    def write_section(self, text, section):
        """IniWrite(pairs, file, section): the section's entries replaced by text's lines."""
        new = [l for l in text.replace('\r\n', '\n').split('\n') if l != '']
        lines = self._load()
        sp = self._span(lines, section)
        if not sp:
            lines += ['[' + section + ']'] + new
        else:
            lines[sp[0] + 1:sp[1]] = new
        self._save(lines)

    def delete(self, section, key=None):
        """IniDelete(file, section[, key])."""
        lines = self._load()
        sp = self._span(lines, section)
        if not sp:
            return
        if key is None:
            del lines[sp[0]:sp[1]]
        else:
            kl = key.lower()
            for i in range(sp[0] + 1, sp[1]):
                kv = self._kv(lines[i])
                if kv and kv[0].lower() == kl:
                    del lines[i]
                    break
        self._save(lines)
