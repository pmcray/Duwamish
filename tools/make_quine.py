"""Generate programs/hofstadter/quine.sal, a SALISH program that prints its
own source text exactly.  The template's @@ marks where the string literal
holding the template itself goes -- Hofstadter's 'quining' made literal."""

import os

TEMPLATE = r'''-- QUINE: a SALISH program whose output is its own source text.
-- Hofstadter, after W. V. Quine: "yields falsehood when preceded by its
-- quotation" yields falsehood when preceded by its quotation.  The
-- string below is the program, quoted; the program is the string, used.
global s := @@

proc quote()
begin
  var c
  putc('"')
  for i := 1 to s[0] do begin
    c := s[i]
    if c = '\n' then prints("\\n")
    else if c = '"' then prints("\\\"")
    else if c = '\\' then prints("\\\\")
    else putc(c)
  end
  putc('"')
end

proc main()
begin
  var i := 1
  while i <= s[0] do begin
    if s[i] = '@' and s[i + 1] = '@' then begin quote(); i := i + 1 end
    else putc(s[i])
    i := i + 1
  end
end
'''


def literal(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "programs", "hofstadter", "quine.sal")
    with open(out, "w") as f:
        f.write(TEMPLATE.replace("@@", literal(TEMPLATE), 1))
    print("wrote", os.path.normpath(out))
