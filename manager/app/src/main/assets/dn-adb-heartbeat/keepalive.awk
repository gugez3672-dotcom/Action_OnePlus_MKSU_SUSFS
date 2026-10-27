# Strict JSON traversal: change only the sole peer of endpoints[tag=wg-adb].
# Preserve every other byte, including credentials and formatting.
function fail() { bad=1; exit 2 }
function ws() { while (substr(doc,pos,1) ~ /^[ \t\r\n]$/ && pos<=length(doc)) pos++ }
function stringToken(   begin,c) {
    begin=pos
    if (substr(doc,pos++,1)!="\"") fail()
    while (pos<=length(doc)) {
        c=substr(doc,pos++,1)
        if (c=="\\") {
            c=substr(doc,pos++,1)
            if (c=="u") {
                if (substr(doc,pos,4)!~/^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$/) fail()
                pos+=4
            } else if (c!~/^["\\\/bfnrt]$/) fail()
        } else if (c=="\"") return substr(doc,begin,pos-begin)
        else if (c ~ /[[:cntrl:]]/) fail()
    }
    fail()
}
function value(owner,field,   c,id,key,begin,raw) {
    ws(); c=substr(doc,pos,1)
    if (c=="{") {
        id=++objects; parent[id]=owner; member[id]=field; pos++; ws()
        if (substr(doc,pos,1)!="}") {
            while (1) {
                ws(); key=stringToken(); ws()
                if (substr(doc,pos++,1)!=":") fail()
                # Duplicate keys elsewhere (e.g. a generator repeating "type")
                # are tolerated like sing-box does; only the target is strict.
                if (++seen[id SUBSEP key]>1) dup[id]=1
                ws(); begin=pos; value(id,key); raw=substr(doc,begin,pos-begin)
                if (key=="\"tag\"") tag[id]=raw
                if (key=="\"type\"") kind[id]=raw
                if (key=="\"persistent_keepalive_interval\"") {
                    ks[id]=begin; ke[id]=pos; kval[id]=raw
                }
                ws(); c=substr(doc,pos++,1)
                if (c=="}") break
                if (c!=",") fail()
            }
        } else pos++
    } else if (c=="[") {
        pos++; ws()
        if (substr(doc,pos,1)=="]") { pos++; return }
        while (1) {
            value(owner,field "[]"); ws(); c=substr(doc,pos++,1)
            if (c=="]") break
            if (c!=",") fail()
        }
    } else if (c=="\"") stringToken()
    else {
        begin=pos
        while (pos<=length(doc)) {
            c=substr(doc,pos,1)
            if (c ~ /^[ \t\r\n]$/ || c=="," || c=="}" || c=="]") break
            pos++
        }
        raw=substr(doc,begin,pos-begin)
        if (raw!="true" && raw!="false" && raw!="null" &&
            raw!~/^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$/) fail()
    }
}
{ doc=doc $0 ORS }
END {
    if (bad) exit 2
    if (interval!="0" && interval!="25") exit 2
    pos=1; value(0,""); ws()
    if (pos<=length(doc)) exit 2
    for (i=1;i<=objects;i++) {
        if (member[i]=="\"endpoints\"[]" && kind[i]=="\"wireguard\"" && tag[i]=="\"wg-adb\"") {
            endpoint=i; endpoints++
        }
    }
    if (endpoints!=1) exit 3
    for (i=1;i<=objects;i++) {
        if (parent[i]==endpoint && member[i]=="\"peers\"[]") { peer=i; peers++ }
    }
    if (dup[endpoint] || dup[peer]) exit 3
    if (peers!=1 || !ks[peer] || kval[peer]!~/^(0|[1-9][0-9]*)$/ || kval[peer]+0>65535) exit 3
    printf "%s%s%s",substr(doc,1,ks[peer]-1),interval,substr(doc,ke[peer])
}
