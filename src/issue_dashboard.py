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
        pid=section(body,"מזהה הפודקאסט")
        episodes=[x.strip() for x in section(body,"פרקים להורדה חוזרת").splitlines() if x.strip()]
        target=section(body,"יעד ההורדה החוזרת")
        if pid not in {p["id"] for p in podcasts}: raise SystemExit("מזהה פודקאסט לא קיים")
        out={"kind":"redownload","ids":pid,"episodes":json.dumps(episodes,ensure_ascii=False),"targets":target}
    elif title.startswith("[הורדה]"):
        raw=section(body,"פודקאסטים")
        ids="" if raw.upper()=="ALL" else ",".join(x.strip() for x in raw.split(",") if x.strip())
        mode="all" if "כל הפרקים" in section(body,"מצב הורדה") else "latest"
        digits=re.search(r"\d+",section(body,"מספר פרקים אחרונים") or "1")
        out={"kind":"download","ids":ids,"mode":mode,"count":str(max(1,min(1000,int(digits.group(0)))) if digits else 1)}
    elif title.startswith("[ניהול פודקאסט]"):
        out={"kind":"manage","action":section(body,"פעולה"),"podcast_id":section(body,"מזהה הפודקאסט"),"name":section(body,"שם"),"rss":section(body,"RSS"),"drive_folder":section(body,"תיקיית Drive"),"yemos_branch":section(body,"שלוחת Yemos")}
    elif title.startswith("[מצב]"):
        out={"kind":"status","scope":section(body,"היקף")}
    else:
        raise SystemExit("Issue לא מזוהה כבקשת ניהול")

    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
        for k,v in out.items():
            f.write(f"{k}={str(v).replace(chr(10),' ')}\n")
if __name__=="__main__": main()
