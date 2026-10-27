package main

// Network history is edited in Go, with the original non-target record bytes
// preserved. Mobile/Wi-Fi histories of users 10/11 and removed apps/users only.
import (
	"bufio"
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var netstatsFileRE = regexp.MustCompile(`^uid(?:_tag)?\.[0-9]+-[0-9]*$`)

type statsRecord struct {
	uid, set, tag int32
	duration      int64
	arrays        [7][]int64
	raw           []byte
}
type statsGroup struct {
	ident     []byte
	identity  string
	transport int // -1 means mixed or unsupported; 0 mobile, 1 Wi-Fi
	rows      []*statsRecord
}
type statsCollection struct{ groups []*statsGroup }
type statsTotals struct {
	Cell    int64 `json:"cellBytes"`
	WiFi    int64 `json:"wifiBytes"`
	CellTag int64 `json:"cellTagBytes"`
	WiFiTag int64 `json:"wifiTagBytes"`
}
type statsResult struct {
	Scope       string      `json:"scope"`
	Before      statsTotals `json:"before"`
	After       statsTotals `json:"after"`
	Changed     int         `json:"changedRecords"`
	DeletedUIDs []int32     `json:"deletedUIDs,omitempty"`
}

// One process handles one click. Populate once from the current inventory.
var statsDeletedUIDs map[int32]bool

func statsFixedUID(uid int32) bool    { return uid == -4 || uid >= 1000000 && uid <= 1199999 }
func statsSelectedUID(uid int32) bool { return statsFixedUID(uid) || statsDeletedUIDs[uid] }
func statsRemovedSelection(users map[int]bool, installed map[int32]bool, histories []int32) (map[int32]bool, error) {
	if !users[0] {
		return nil, errors.New("owner user inventory unavailable")
	}
	removed := map[int32]bool{}
	for _, uid := range histories {
		if uid < 0 || statsFixedUID(uid) {
			continue
		}
		user, app := int(uid/100000), uid%100000
		if !users[user] || app >= 10000 && app <= 19999 && !installed[uid] {
			removed[uid] = true
		}
	}
	return removed, nil
}

type statsCursor struct {
	raw []byte
	pos int
}

func (c *statsCursor) take(n int) ([]byte, error) {
	if n < 0 || n > len(c.raw)-c.pos {
		return nil, io.ErrUnexpectedEOF
	}
	b := c.raw[c.pos : c.pos+n]
	c.pos += n
	return b, nil
}
func (c *statsCursor) i32() (int32, error) {
	b, e := c.take(4)
	if e != nil {
		return 0, e
	}
	return int32(binary.BigEndian.Uint32(b)), nil
}
func (c *statsCursor) i64() (int64, error) {
	b, e := c.take(8)
	if e != nil {
		return 0, e
	}
	return int64(binary.BigEndian.Uint64(b)), nil
}
func (c *statsCursor) count(max int) (int, error) {
	n, e := c.i32()
	if e != nil {
		return 0, e
	}
	if n < 0 || int(n) > max {
		return 0, errors.New("invalid ANET count")
	}
	return int(n), nil
}
func (c *statsCursor) str() error {
	b, e := c.take(1)
	if e != nil {
		return e
	}
	if b[0] == 0 {
		return nil
	}
	if b[0] != 1 {
		return errors.New("invalid ANET string")
	}
	n, e := c.take(2)
	if e != nil {
		return e
	}
	_, e = c.take(int(binary.BigEndian.Uint16(n)))
	return e
}
func (c *statsCursor) array() ([]int64, error) {
	n, e := c.i32()
	if e != nil {
		return nil, e
	}
	if n == -1 {
		return nil, nil
	}
	if n < 0 || n > 1000000 || int(n) > len(c.raw)-c.pos {
		return nil, errors.New("invalid ANET array size")
	}
	a := make([]int64, int(n))
	for i := range a {
		var v uint64
		done := false
		for shift := 0; shift < 64; shift += 7 {
			b, e := c.take(1)
			if e != nil {
				return nil, e
			}
			if shift == 63 && b[0] > 0 {
				return nil, errors.New("ANET integer overflow")
			}
			v |= uint64(b[0]&127) << shift
			if b[0]&128 == 0 {
				done = true
				break
			}
		}
		if !done || v > math.MaxInt64 {
			return nil, errors.New("invalid ANET varlong")
		}
		a[i] = int64(v)
	}
	return a, nil
}
func statsParse(raw []byte) (*statsCollection, error) {
	c := statsCursor{raw: raw}
	magic, e := c.i32()
	if e != nil {
		return nil, e
	}
	version, e := c.i32()
	if e != nil {
		return nil, e
	}
	if magic != 1095648596 || version != 16 {
		return nil, errors.New("unsupported network statistics format")
	}
	ng, e := c.count(100000)
	if e != nil {
		return nil, e
	}
	result := &statsCollection{}
	seen := map[string]bool{}
	for gi := 0; gi < ng; gi++ {
		start := c.pos
		iv, e := c.i32()
		if e != nil {
			return nil, e
		}
		if iv != 7 {
			return nil, errors.New("unsupported network identity format")
		}
		ni, e := c.count(1000)
		if e != nil {
			return nil, e
		}
		g := &statsGroup{transport: -1}
		ids := []string{}
		mixed := ni == 0
		for i := 0; i < ni; i++ {
			s := c.pos
			kind, e := c.i32()
			if e != nil {
				return nil, e
			}
			if _, e = c.i32(); e != nil {
				return nil, e
			}
			if e = c.str(); e != nil {
				return nil, e
			}
			if e = c.str(); e != nil {
				return nil, e
			}
			if _, e = c.take(11); e != nil {
				return nil, e
			}
			if kind != 0 && kind != 1 {
				mixed = true
			}
			if i == 0 {
				g.transport = int(kind)
			} else if g.transport != int(kind) {
				mixed = true
			}
			ids = append(ids, string(raw[s:c.pos]))
		}
		if mixed {
			g.transport = -1
		}
		sort.Strings(ids)
		var canonical bytes.Buffer
		for _, id := range ids {
			_ = binary.Write(&canonical, binary.BigEndian, uint32(len(id)))
			canonical.WriteString(id)
		}
		g.identity = canonical.String()
		g.ident = raw[start:c.pos]
		if seen[g.identity] {
			return nil, errors.New("duplicate network identity")
		}
		seen[g.identity] = true
		nr, e := c.count(100000)
		if e != nil {
			return nil, e
		}
		keys := map[[3]int32]bool{}
		for ri := 0; ri < nr; ri++ {
			s := c.pos
			r := &statsRecord{}
			if r.uid, e = c.i32(); e != nil {
				return nil, e
			}
			if r.set, e = c.i32(); e != nil {
				return nil, e
			}
			if r.tag, e = c.i32(); e != nil {
				return nil, e
			}
			hv, e := c.i32()
			if e != nil {
				return nil, e
			}
			if hv != 3 {
				return nil, errors.New("unsupported network history format")
			}
			if r.duration, e = c.i64(); e != nil {
				return nil, e
			}
			if r.duration <= 0 {
				return nil, errors.New("invalid history duration")
			}
			for j := range r.arrays {
				if r.arrays[j], e = c.array(); e != nil {
					return nil, e
				}
			}
			if r.arrays[0] == nil || r.arrays[2] == nil || r.arrays[4] == nil {
				return nil, errors.New("missing required history array")
			}
			for j := 1; j < 7; j++ {
				if r.arrays[j] != nil && len(r.arrays[j]) != len(r.arrays[0]) {
					return nil, errors.New("history array length mismatch")
				}
			}
			for j := 1; j < len(r.arrays[0]); j++ {
				if r.arrays[0][j] <= r.arrays[0][j-1] {
					return nil, errors.New("unsorted history buckets")
				}
			}
			key := [3]int32{r.uid, r.set, r.tag}
			if keys[key] {
				return nil, errors.New("duplicate UID history")
			}
			keys[key] = true
			r.raw = raw[s:c.pos]
			g.rows = append(g.rows, r)
		}
		result.groups = append(result.groups, g)
	}
	if c.pos != len(raw) {
		return nil, errors.New("trailing network statistics bytes")
	}
	return result, nil
}
func statsWriteArray(b *bytes.Buffer, a []int64) {
	if a == nil {
		_ = binary.Write(b, binary.BigEndian, int32(-1))
		return
	}
	_ = binary.Write(b, binary.BigEndian, int32(len(a)))
	for _, n := range a {
		v := uint64(n)
		for v > 127 {
			b.WriteByte(byte(v&127) | 128)
			v >>= 7
		}
		b.WriteByte(byte(v))
	}
}
func (r *statsRecord) encode() []byte {
	var b bytes.Buffer
	for _, n := range []int32{r.uid, r.set, r.tag, 3} {
		_ = binary.Write(&b, binary.BigEndian, n)
	}
	_ = binary.Write(&b, binary.BigEndian, r.duration)
	for _, a := range r.arrays {
		statsWriteArray(&b, a)
	}
	return b.Bytes()
}
func (c *statsCollection) encode() []byte {
	var b bytes.Buffer
	for _, n := range []int32{1095648596, 16, int32(len(c.groups))} {
		_ = binary.Write(&b, binary.BigEndian, n)
	}
	for _, g := range c.groups {
		b.Write(g.ident)
		_ = binary.Write(&b, binary.BigEndian, int32(len(g.rows)))
		for _, r := range g.rows {
			b.Write(r.raw)
		}
	}
	return b.Bytes()
}
func statsTarget(g *statsGroup, r *statsRecord) bool {
	return g.transport >= 0 && statsSelectedUID(r.uid)
}
func statsAdd(a, b int64) (int64, error) {
	if a < 0 || b < 0 || a > math.MaxInt64-b {
		return 0, errors.New("network counter overflow")
	}
	return a + b, nil
}
func (t *statsTotals) add(kind int, tag bool, n int64) error {
	p := &t.Cell
	if kind == 1 {
		p = &t.WiFi
	}
	if tag {
		p = &t.CellTag
		if kind == 1 {
			p = &t.WiFiTag
		}
	}
	v, e := statsAdd(*p, n)
	if e == nil {
		*p = v
	}
	return e
}
func statsFilter(raw []byte, tag bool) ([]byte, statsTotals, int, error) {
	c, e := statsParse(raw)
	if e != nil {
		return nil, statsTotals{}, 0, e
	}
	if !bytes.Equal(raw, c.encode()) {
		return nil, statsTotals{}, 0, errors.New("network history roundtrip differs")
	}
	totals := statsTotals{}
	changed := 0
	for _, g := range c.groups {
		for _, r := range g.rows {
			if !statsTarget(g, r) {
				continue
			}
			for i := range r.arrays[0] {
				n, e := statsAdd(r.arrays[2][i], r.arrays[4][i])
				if e != nil {
					return nil, totals, 0, e
				}
				if e = totals.add(g.transport, tag, n); e != nil {
					return nil, totals, 0, e
				}
			}
			for j := 1; j < 7; j++ {
				for i := range r.arrays[j] {
					r.arrays[j][i] = 0
				}
			}
			next := r.encode()
			if !bytes.Equal(next, r.raw) {
				changed++
			}
			r.raw = next
		}
	}
	next := c.encode()
	if e = statsValidateFilter(raw, next); e != nil {
		return nil, totals, 0, e
	}
	return next, totals, changed, nil
}
func statsValidateFilter(before, after []byte) error {
	a, e := statsParse(before)
	if e != nil {
		return e
	}
	b, e := statsParse(after)
	if e != nil {
		return e
	}
	if len(a.groups) != len(b.groups) {
		return errors.New("identity groups changed")
	}
	for i, g := range a.groups {
		h := b.groups[i]
		if !bytes.Equal(g.ident, h.ident) || len(g.rows) != len(h.rows) {
			return errors.New("identity or UID keys changed")
		}
		for j, r := range g.rows {
			s := h.rows[j]
			if r.uid != s.uid || r.set != s.set || r.tag != s.tag || r.duration != s.duration {
				return errors.New("UID key changed")
			}
			if !statsTarget(g, r) {
				if !bytes.Equal(r.raw, s.raw) {
					return errors.New("non-target history changed")
				}
				continue
			}
			for k, old := range r.arrays {
				now := s.arrays[k]
				if (old == nil) != (now == nil) || len(old) != len(now) {
					return errors.New("history shape changed")
				}
				for n, v := range old {
					want := int64(0)
					if k == 0 {
						want = v
					}
					if now[n] != want {
						return errors.New("target history not zero or times changed")
					}
				}
			}
		}
	}
	return nil
}
func statsMergeRecord(a, b *statsRecord) (*statsRecord, error) {
	if b == nil {
		return a, nil
	}
	if a.uid != b.uid || a.set != b.set || a.tag != b.tag || a.duration != b.duration {
		return nil, errors.New("rollback history key differs")
	}
	buckets := map[int64][7]int64{}
	enabled := [7]bool{true}
	for _, r := range []*statsRecord{a, b} {
		for j := 1; j < 7; j++ {
			enabled[j] = enabled[j] || r.arrays[j] != nil
		}
		for i, t := range r.arrays[0] {
			v := buckets[t]
			for j := 1; j < 7; j++ {
				if r.arrays[j] != nil {
					n, e := statsAdd(v[j], r.arrays[j][i])
					if e != nil {
						return nil, e
					}
					v[j] = n
				}
			}
			buckets[t] = v
		}
	}
	times := make([]int64, 0, len(buckets))
	for t := range buckets {
		times = append(times, t)
	}
	sort.Slice(times, func(i, j int) bool { return times[i] < times[j] })
	r := &statsRecord{uid: a.uid, set: a.set, tag: a.tag, duration: a.duration}
	for j, on := range enabled {
		if on {
			r.arrays[j] = make([]int64, len(times))
		}
	}
	for i, t := range times {
		r.arrays[0][i] = t
		v := buckets[t]
		for j := 1; j < 7; j++ {
			if enabled[j] {
				r.arrays[j][i] = v[j]
			}
		}
	}
	r.raw = r.encode()
	return r, nil
}
func statsMergeTarget(before, current []byte) ([]byte, error) {
	a, e := statsParse(before)
	if e != nil {
		return nil, e
	}
	b, e := statsParse(current)
	if e != nil {
		return nil, e
	}
	for _, old := range a.groups {
		for _, r := range old.rows {
			if !statsTarget(old, r) {
				continue
			}
			var group *statsGroup
			for _, g := range b.groups {
				if g.identity == old.identity {
					group = g
					break
				}
			}
			if group == nil {
				group = &statsGroup{ident: old.ident, identity: old.identity, transport: old.transport}
				b.groups = append(b.groups, group)
			}
			index := -1
			var now *statsRecord
			for i, s := range group.rows {
				if r.uid == s.uid && r.set == s.set && r.tag == s.tag {
					index = i
					now = s
					break
				}
			}
			merged, e := statsMergeRecord(r, now)
			if e != nil {
				return nil, e
			}
			if index < 0 {
				group.rows = append(group.rows, merged)
			} else {
				group.rows[index] = merged
			}
		}
	}
	out := b.encode()
	_, e = statsParse(out)
	return out, e
}

var statsDumpUIDRE = regexp.MustCompile(`\] uid=(-?[0-9]+) set=`)
var statsDumpTypeRE = regexp.MustCompile(`\{type=(-?[0-9]+),`)

// --full reads getOrLoadCompleteLocked(), the same weak cached collection used
// by application sessions. Both UID sections must be present to accept zero.
func statsParseDump(text string) (statsTotals, error) {
	totals := statsTotals{}
	section := ""
	uidSeen, tagSeen, uidFull, tagFull := false, false, false, false
	target := false
	kind := -1
	scanner := bufio.NewScanner(strings.NewReader(text))
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	for scanner.Scan() {
		s := strings.TrimSpace(scanner.Text())
		switch s {
		case "UID stats:":
			section = "uid"
			uidSeen = true
			target = false
			continue
		case "UID tag stats:":
			section = "tag"
			tagSeen = true
			target = false
			continue
		case "InterfaceMapHelper:":
			section = ""
			target = false
			continue
		case "Complete history:":
			if section == "uid" {
				uidFull = true
			}
			if section == "tag" {
				tagFull = true
			}
			continue
		}
		if section == "" {
			continue
		}
		if strings.HasPrefix(s, "ident=") {
			target = false
			kind = -1
			m := statsDumpUIDRE.FindStringSubmatch(s)
			types := statsDumpTypeRE.FindAllStringSubmatch(s, -1)
			if len(m) != 2 || len(types) == 0 {
				return totals, errors.New("unrecognized live history identity")
			}
			id, e := strconv.Atoi(m[1])
			if e != nil {
				return totals, e
			}
			allowed := true
			for i, t := range types {
				k, e := strconv.Atoi(t[1])
				if e != nil {
					return totals, e
				}
				if k != 0 && k != 1 {
					allowed = false
				}
				if i == 0 {
					kind = k
				} else if kind != k {
					allowed = false
				}
			}
			target = allowed && statsSelectedUID(int32(id))
			continue
		}
		if !target || !strings.HasPrefix(s, "st=") {
			continue
		}
		var rb, tb int64
		gotRB, gotTB := false, false
		for _, f := range strings.Fields(s) {
			if strings.HasPrefix(f, "rb=") {
				n, e := strconv.ParseInt(strings.TrimPrefix(f, "rb="), 10, 64)
				if e != nil {
					return totals, e
				}
				rb = n
				gotRB = true
			}
			if strings.HasPrefix(f, "tb=") {
				n, e := strconv.ParseInt(strings.TrimPrefix(f, "tb="), 10, 64)
				if e != nil {
					return totals, e
				}
				tb = n
				gotTB = true
			}
		}
		if !gotRB || !gotTB {
			return totals, errors.New("incomplete live history bucket")
		}
		n, e := statsAdd(rb, tb)
		if e != nil {
			return totals, e
		}
		if e = totals.add(kind, section == "tag", n); e != nil {
			return totals, e
		}
	}
	if e := scanner.Err(); e != nil {
		return totals, e
	}
	if !uidSeen || !tagSeen || !uidFull || !tagFull {
		return totals, fmt.Errorf("complete UID and tag histories unavailable")
	}
	return totals, nil
}
