import json, os, re
from pathlib import Path

def section(body, label):
    m=re.search(r"(?ms)^### "+re.escape(label)+r"\s*\n+(.+?)(?=\n### |\Z)", body or "")
    return m.group(1).strip() if m else ""

def main():
    body=os.environ.get("ISSUE_BODY","")
    title=os.environ.get("ISSUE_TITLE","")
    config=json.loads(Path("config/podcasts.json").read_text(encoding="utf-8"))
    podcasts=config.get("podcasts",[])
    out={}

    if title.startswith("[הורדה חוזרת]"):
        selected=section(body,"בחירת פודקאסטים")
        names={p["name"]:p["id"] for p in podcasts}
        ids=[pid for name,pid in names.items() if re.search(r"(?mi)^- \[x\] "+re.escape(name)+r"\s*$",selected)]
        episodes=[x.strip() for x in section(body,"פרקים מסוימים להורדה חוזרת").splitlines() if x.strip()]
        count_text=section(body,"כמות פרקים אחרונים להורדה חוזרת")
        digits=re.search(r"\d+",count_text)
        count=str(max(1,min(1000,int(digits.group(0))))) if digits else ""
        target=section(body,"יעד ההורדה החוזרת")
        if not ids: raise SystemExit("לא נבחר אף פודקאסט")
        if not episodes and not count: raise SystemExit("יש להגדיר כמות פרקים אחרונים או לבחור פרקים מסוימים")
        out={"kind":"redownload","ids":",".join(ids),"episodes":json.dumps(episodes,ensure_ascii=False),"force_count":count,"targets":target}
    elif title.startswith("[הורדה]"):
        selected=section(body,"בחירת פודקאסטים")
        names={p["name"]:p["id"] for p in podcasts}
        all_selected=bool(re.search(r"(?mi)^- \[x\] כל הפודקאסטים הפעילים\s*$",selected))
        ids="" if all_selected else ",".join(pid for name,pid in names.items() if re.search(r"(?mi)^- \[x\] "+re.escape(name)+r"\s*$",selected))
        if not all_selected and not ids: raise SystemExit("לא נבחר אף פודקאסט")
        mode="all" if "כל הפרקים" in section(body,"מצב הורדה") else "latest"
        digits=re.search(r"\d+",section(body,"מספר פרקים אחרונים") or "1")
        out={"kind":"download","ids":ids,"mode":mode,"count":str(max(1,min(1000,int(digits.group(0)))) if digits else 1)}
    elif title.startswith("[ניהול פודקאסט]"):
        out={"kind":"manage","action":section(body,"פעולה"),"current_name":section(body,"שם הפודקאסט הקיים"),"name":section(body,"שם"),"rss":section(body,"RSS"),"drive_folder":section(body,"תיקיית Drive"),"yemos_branch":section(body,"שלוחת Yemos")}
    elif title.startswith("[מצב]"):
        out={"kind":"status","scope":section(body,"היקף")}
    elif title.startswith("[רשימת פודקאסטים]"):
        out={"kind":"podcast_list","scope":section(body,"מה להציג")}
    else:
        raise SystemExit("Issue לא מזוהה כבקשת ניהול")

    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
        for k,v in out.items():
            f.write(f"{k}={str(v).replace(chr(10),' ')}\n")
if __name__=="__main__": main()
