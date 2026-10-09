"""Зведення по пунктах із textbook.json: блоки, нумерація (прогалини), складність, підпункти, статуси виразів.

Запуск: python tools/pipeline_audit.py pipeline_out/math_merzlyak_5/textbook.json
"""
import json, collections, sys
d=json.load(open(sys.argv[1]))
for sec in d['sections']:
  for par in sec['paragraphs']:
    for it in par['items']:
        print(f"\n=== п.{it['number']} {it['title']}  (стор. {it['source']['pdf_page']}) ===")
        for b in it['blocks']:
            exs=b['exercises']
            nums=[e['number'] for e in exs]
            ints=[int(n) for n in nums if n.isdigit()]
            gaps=[n for n in range(min(ints),max(ints)+1) if n not in ints] if ints else []
            diff=collections.Counter(e['difficulty'] or '-' for e in exs)
            subs=sum(len(e['subexercises']) for e in exs)
            nr=sum(e['needs_review'] for e in exs)+sum(s['needs_review'] for e in exs for s in e['subexercises'])
            ex_status=collections.Counter(s.get('expr_status','-') for e in exs for s in e['subexercises'])
            print(f" {b['type']:16} стор.{b['source']['pdf_page']:>2} вправ {len(exs):>2} {nums[:1]}..{nums[-1:]} прогалини={gaps} складн={dict(diff)} підп={subs} review={nr} expr={dict(ex_status)} рис={len(b['figure_ids'])} дом={sum(e['homework'] for e in exs)}")
