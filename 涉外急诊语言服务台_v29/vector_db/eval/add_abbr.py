# -*- coding: utf-8 -*-
import json
from openpyxl import load_workbook
p="work/merge/涉外急诊与东盟文化_中英术语语料总库_V1.3.xlsx"
wb=load_workbook(p, read_only=True, data_only=True)
ws=wb["专业术语总表"]
alias=json.load(open("work/vector_db/index/aliases.json",encoding="utf-8"))
n=0
for row in ws.iter_rows(min_row=2, values_only=True):
    abbr=row[7]; zh=row[5]
    if abbr and str(abbr).strip() and zh:
        a=str(abbr).strip()
        alias.setdefault(a, []).append(str(zh).strip()); n+=1
# 常见中文缩写/口语补充
extra={
 "心梗":["心肌梗死"],"脑梗":["脑梗死"],"中风":["脑卒中"],"肺栓塞":["肺栓塞"],
 "插管":["气管插管"],"除颤":["电除颤"],"按压":["胸外按压"],"上呼吸机":["机械通气"],
 "血压高":["高血压"],"血糖高":["高血糖"],"血糖低":["低血糖"],"输血":["输血"],
 "拍片":["X线检查"],"做CT":["CT检查"],"做核磁":["MRI检查"],"验血":["血常规","静脉采血"],
 "打点滴":["静脉输液"],"挂水":["静脉输液"],"皮试":["皮肤试验"],"破伤风针":["破伤风免疫球蛋白"],
}
for k,v in extra.items(): alias.setdefault(k,[]).extend(v)
json.dump(alias, open("work/vector_db/index/aliases.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("缩写别名", n, "总别名组", len(alias))
