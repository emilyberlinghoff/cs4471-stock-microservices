"""Rebuild PR2 vector/PDF and PNG architecture diagrams with matplotlib."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT=Path(__file__).resolve().parents[1]/"docs/pr2/figures"
OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":13})

def canvas(title):
    fig,ax=plt.subplots(figsize=(11,7.5));fig.subplots_adjust(.03,.06,.97,.89)
    ax.set(xlim=(0,11),ylim=(0,7));ax.axis("off");fig.suptitle(title,fontsize=20,fontweight="bold")
    return fig,ax

def box(ax,x,y,text,w=2.7,h=1.1,planned=False):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.08",facecolor="#eef4fb" if not planned else "#fff6e6",edgecolor="#224b73",linewidth=1.5,linestyle="--" if planned else "-"))
    ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=13)

def arrow(ax,a,b,label="",planned=False):
    ax.annotate("",xy=b,xytext=a,arrowprops=dict(arrowstyle="->",lw=1.5,color="#224b73",linestyle="--" if planned else "-"))
    if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.13,label,ha="center",va="bottom",fontsize=10,bbox=dict(fc="white",ec="none",pad=1))

def save(fig,name):
    for ext in ["png","svg","pdf"]:fig.savefig(OUT/f"{name}.{ext}",dpi=180)
    plt.close(fig)

fig,ax=canvas("Module view: independently developed service units")
box(ax,4.1,5.6,"Stock analytics source\nSeparate branches\nmain not integrated")
for x,text in [(0.1,"Consumer GUI\nclient/index.html"),(4.1,"Registry integration\nLease client\nExternal image"),(8.1,"Stock services\nS2 / S3 / S4 / S5")]:
    box(ax,x,3.8,text);arrow(ax,(5.45,5.6),(x+1.35,4.9))
box(ax,.1,1.6,"S4 module chain\nHTTP → validation → orchestration\n→ provider / SMA core",w=4.8,h=1.4)
box(ax,6.1,1.6,"S5 module chain\nHTTP → validation → orchestration\n→ provider / comparison core",w=4.8,h=1.4)
arrow(ax,(9.45,3.8),(2.5,3.0));arrow(ax,(9.45,3.8),(8.5,3.0))
ax.text(5.5,.65,"Arrows from source root mean decomposition. Service chains mean code dependencies.\nS4 and S5 do not import or call one another. Both contain the same lease-client module.",ha="center",fontsize=12)
save(fig,"module")

fig,ax=canvas("Component-and-Connector view: implemented and planned links")
box(ax,.2,5.2,"User / browser",w=2.4)
box(ax,4.0,5.2,"Consumer GUI\nCurrent direct S3 call",w=3)
box(ax,8.2,5.2,"Primary registry\nBackup registry",w=2.5)
arrow(ax,(2.6,5.75),(4,5.75),"HTTP")
arrow(ax,(7,5.75),(8.2,5.75),"Discovery",planned=True)
for x,name in [(0.2,"S2\nReturns"),(3.0,"S3\nVolatility"),(5.8,"S4\nMoving averages"),(8.6,"S5\nComparison")]:
    box(ax,x,2.9,name,w=2.2)
    arrow(ax,(x+1.1,2.9),(5.45,1.7),planned=False)
box(ax,4,0.6,"Alpha Vantage\nLive entitlement unverified",w=3)
arrow(ax,(5.45,5.2),(4.1,4),"Current S3 call")
arrow(ax,(5.45,5.2),(6.9,4),"GUI integration",planned=True)
arrow(ax,(5.45,5.2),(9.7,4),planned=True)
arrow(ax,(9.45,4),(9.45,5.2),"S4/S5 leases\nlocal tested")
ax.text(.25,.65,"Solid: implemented code\nDashed: planned integration\nS1: planned, absent from branches",fontsize=11)
save(fig,"components")

fig,ax=canvas("Communication quality view: request and response sequence")
lanes=["Consumer","HTTP API","Validation /\ncalendar","Data\nadapter","Alpha\nVantage","Calculation\ncore"]
xs=[.65,2.6,4.55,6.5,8.45,10.35]
for x,name in zip(xs,lanes):
    ax.text(x,6.6,name,ha="center",fontsize=12,fontweight="bold")
    ax.plot([x,x],[.7,6.2],color="#a9b7c5",linestyle="--",lw=1)
steps=[(0,1,"1. Request symbols + dates"),(1,2,"2. Validate; determine sessions"),(2,1,"3. Reject invalid input: 400"),(1,3,"4. Fetch required closes"),(3,4,"5. Daily JSON request(s)"),(4,3,"6. Data OR provider error"),(3,1,"7. Preserve gaps / report failure"),(1,5,"8. Calculate only usable data"),(5,1,"9. Dated averages / ranking"),(1,0,"10. JSON + HTTP status")]
for i,(a,b,label) in enumerate(steps):
    y=5.9-i*.49
    ax.annotate("",xy=(xs[b],y),xytext=(xs[a],y),arrowprops=dict(arrowstyle="->",lw=1.5,color="#224b73"))
    ax.text((xs[a]+xs[b])/2,y+.08,label,ha="center",fontsize=10.5,bbox=dict(fc="white",ec="none",pad=.5))
ax.text(5.5,.25,"Step 3 is an early-return branch; steps 4–9 occur only after valid input.\nS5 makes 2–5 concurrent provider requests; any failed stock produces no ranking.",ha="center",fontsize=11)
save(fig,"communication")

fig,ax=canvas("Communication quality view: registry lease behaviour")
for x,y,label in [(0.4,4.8,"Unregistered"),(4.1,4.8,"Registered\nlease maintained"),(8.0,4.8,"Registry unavailable"),(4.1,1.7,"Stopping\nno more heartbeats"),(8.0,1.7,"Removed after\nlease expiry")]:box(ax,x,y,label,w=2.6)
arrow(ax,(3,5.35),(4.1,5.35),"POST /register 200")
arrow(ax,(6.7,5.35),(8,5.35),"HTTP / network error")
arrow(ax,(8,4.9),(6.7,4.9),"Later re-register succeeds")
arrow(ax,(5.4,4.8),(5.4,2.8),"SIGINT / SIGTERM")
arrow(ax,(6.7,2.25),(8,2.25),"10 s lease + prune")
arrow(ax,(4.2,5.1),(2.7,4.8),"Unknown-node 404")
ax.text(5.5,.7,"Maintain each configured registry independently. Heartbeat interval: 3 s.\nVerified image: no DELETE endpoint; immediate removal requires registry-owner support.",ha="center",fontsize=12)
save(fig,"leases")

fig,ax=canvas("System context and ownership overlay")
box(ax,.2,5.2,"Users / team\nBrowser or CLI",w=3)
box(ax,4,3.6,"Stock analytics boundary\nRegistry + GUI + services",w=3,h=1.6)
box(ax,8,5.2,"Alpha Vantage\nExternal data provider",w=2.7)
box(ax,.2,1.0,"Gordon / Max\nGUI, contracts, S1/S2",w=3)
box(ax,4,1,"Emily\nS4/S5 + architecture",w=3)
box(ax,8,1,"Aashka\nRegistry / cloud / S3",w=2.7)
arrow(ax,(3.2,5.75),(4,4.5),"Consumer HTTP")
arrow(ax,(7,4.5),(8,5.75),"Provider HTTPS")
for x in [1.7,5.5,9.35]:arrow(ax,(x,2.1),(5.5,3.6),"Ownership")
ax.text(5.5,.25,"Ownership comes from the workbook; it describes responsibility, not verified completion.\nCloud is the intended deployment context; the new lifecycle evidence is local.",ha="center",fontsize=12)
save(fig,"context")
print(OUT)
