package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const netstatsDir = "/data/misc/apexdata/com.android.tethering/netstats"

type statsPause struct {
	pid     int
	start   string
	until   time.Time
	writer  *os.File
	child   *exec.Cmd
	resumed bool
}

func statsProcessStart(pid int) (string, error) {
	p := filepath.Join("/proc", strconv.Itoa(pid))
	name, e := os.ReadFile(filepath.Join(p, "comm"))
	if e != nil {
		return "", e
	}
	if strings.TrimSpace(string(name)) != "system_server" {
		return "", errors.New("unexpected system process")
	}
	b, e := os.ReadFile(filepath.Join(p, "stat"))
	if e != nil {
		return "", e
	}
	end := strings.LastIndexByte(string(b), ')')
	if end < 0 {
		return "", errors.New("unexpected process stat")
	}
	f := strings.Fields(string(b[end+1:]))
	if len(f) < 20 {
		return "", errors.New("short process stat")
	}
	return f[19], nil
}

// The same binary is a short-lived safety child only during a click. It blocks
// on a pipe, resumes on parent death/completion, or at one 8-second deadline.
// There is no loop, recurring timer, boot hook, shell or resident service.
func netstatsGuard(args []string) error {
	if len(args) != 2 {
		return errors.New("invalid pause guard arguments")
	}
	pid, e := strconv.Atoi(args[0])
	if e != nil || pid <= 1 {
		return errors.New("invalid guard PID")
	}
	start, e := statsProcessStart(pid)
	if e != nil || start != args[1] {
		return errors.New("guard process changed")
	}
	f := os.NewFile(3, "pause-parent")
	if f == nil {
		return errors.New("guard pipe missing")
	}
	defer f.Close()
	fmt.Println("READY")
	done := make(chan struct{}, 1)
	go func() { var b [1]byte; _, _ = f.Read(b[:]); done <- struct{}{} }()
	timer := time.NewTimer(8 * time.Second)
	defer timer.Stop()
	select {
	case <-done:
	case <-timer.C:
	}
	if current, e := statsProcessStart(pid); e == nil && current == start {
		return syscall.Kill(pid, syscall.SIGCONT)
	}
	return nil
}
func statsFreeze(pid int) (*statsPause, error) {
	start, e := statsProcessStart(pid)
	if e != nil {
		return nil, e
	}
	exe, e := os.Executable()
	if e != nil {
		return nil, e
	}
	r, w, e := os.Pipe()
	if e != nil {
		return nil, e
	}
	child := exec.Command(exe, "netstats-guard", strconv.Itoa(pid), start)
	child.ExtraFiles = []*os.File{r}
	out, e := child.StdoutPipe()
	if e != nil {
		r.Close()
		w.Close()
		return nil, e
	}
	if e = child.Start(); e != nil {
		r.Close()
		w.Close()
		return nil, e
	}
	r.Close()
	p := &statsPause{pid: pid, start: start, until: time.Now().Add(6 * time.Second), writer: w, child: child}
	ready := make(chan string, 1)
	go func() { s, _ := bufio.NewReader(out).ReadString('\n'); ready <- strings.TrimSpace(s) }()
	select {
	case s := <-ready:
		if s != "READY" {
			p.resume()
			return nil, errors.New("pause guard did not initialize")
		}
	case <-time.After(2 * time.Second):
		p.resume()
		return nil, errors.New("pause guard start timed out")
	}
	if e = syscall.Kill(pid, syscall.SIGSTOP); e != nil {
		p.resume()
		return nil, e
	}
	time.Sleep(50 * time.Millisecond)
	threads, e := os.ReadDir(filepath.Join("/proc", strconv.Itoa(pid), "task"))
	if e != nil {
		p.resume()
		return nil, e
	}
	for _, t := range threads {
		b, e := os.ReadFile(filepath.Join("/proc", strconv.Itoa(pid), "task", t.Name(), "status"))
		if e != nil {
			p.resume()
			return nil, e
		}
		stopped := false
		for _, line := range strings.Split(string(b), "\n") {
			if strings.HasPrefix(line, "State:") {
				f := strings.Fields(line)
				stopped = len(f) > 1 && f[1] == "T"
				break
			}
		}
		if !stopped {
			p.resume()
			return nil, errors.New("system process did not fully pause")
		}
	}
	if e = p.check(); e != nil {
		p.resume()
		return nil, e
	}
	return p, nil
}
func (p *statsPause) check() error {
	if p.resumed || time.Now().After(p.until) {
		return errors.New("statistics pause deadline reached")
	}
	s, e := statsProcessStart(p.pid)
	if e != nil {
		return e
	}
	if s != p.start {
		return errors.New("system process changed")
	}
	return nil
}
func (p *statsPause) resume() {
	if p == nil || p.resumed {
		return
	}
	p.resumed = true
	if s, e := statsProcessStart(p.pid); e == nil && s == p.start {
		_ = syscall.Kill(p.pid, syscall.SIGCONT)
	}
	_ = p.writer.Close()
	_ = p.child.Wait()
}
func statsCommand(timeout time.Duration, name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	out, e := exec.CommandContext(ctx, "/system/bin/"+name, args...).CombinedOutput()
	if e != nil {
		return "", fmt.Errorf("%s: %s (%w)", name, short(strings.TrimSpace(string(out))), e)
	}
	return string(out), nil
}
func statsReadLive() (statsTotals, error) {
	s, e := statsCommand(12*time.Second, "dumpsys", "netstats", "--full", "--uid", "--tag")
	if e != nil {
		return statsTotals{}, e
	}
	return statsParseDump(s)
}
func statsPrepareSelection() (statsTotals, error) {
	s, e := statsCommand(12*time.Second, "dumpsys", "netstats", "--full", "--uid", "--tag")
	if e != nil {
		return statsTotals{}, e
	}
	userText, e := statsCommand(3*time.Second, "pm", "list", "users")
	if e != nil {
		return statsTotals{}, e
	}
	users := map[int]bool{}
	for _, m := range userIDPattern.FindAllStringSubmatch(userText, -1) {
		id, e := strconv.Atoi(m[1])
		if e != nil {
			return statsTotals{}, e
		}
		users[id] = true
	}
	if !users[0] {
		return statsTotals{}, errors.New("owner user inventory unavailable")
	}
	histories := []int32{}
	needed := map[int]bool{}
	for _, m := range statsDumpUIDRE.FindAllStringSubmatch(s, -1) {
		n, e := strconv.ParseInt(m[1], 10, 32)
		if e != nil {
			return statsTotals{}, e
		}
		uid := int32(n)
		histories = append(histories, uid)
		if uid >= 0 && !statsFixedUID(uid) && uid%100000 >= 10000 && uid%100000 <= 19999 && users[int(uid/100000)] {
			needed[int(uid/100000)] = true
		}
	}
	installed := map[int32]bool{}
	for user := range needed {
		packages, e := statsCommand(4*time.Second, "cmd", "package", "list", "packages", "-U", "--user", strconv.Itoa(user))
		if e != nil {
			return statsTotals{}, e
		}
		count := 0
		for _, line := range strings.Split(packages, "\n") {
			if strings.TrimSpace(line) == "" {
				continue
			}
			fields := strings.Fields(line)
			if len(fields) != 2 || !strings.HasPrefix(fields[0], "package:") || !strings.HasPrefix(fields[1], "uid:") {
				return statsTotals{}, errors.New("unexpected installed package inventory")
			}
			n, e := strconv.ParseInt(strings.TrimPrefix(fields[1], "uid:"), 10, 32)
			if e != nil || n < 0 || int(n/100000) != user {
				return statsTotals{}, errors.New("installed package UID scope mismatch")
			}
			installed[int32(n)] = true
			count++
		}
		if count == 0 {
			return statsTotals{}, errors.New("installed package inventory unavailable")
		}
	}
	statsDeletedUIDs, e = statsRemovedSelection(users, installed, histories)
	if e != nil {
		return statsTotals{}, e
	}
	return statsParseDump(s)
}
func statsPersist() error {
	_, e := statsCommand(6*time.Second, "dumpsys", "netstats", "--poll")
	return e
}
func statsSnapshot(dir string) (map[string][]byte, error) {
	entries, e := os.ReadDir(dir)
	if e != nil {
		return nil, e
	}
	files := map[string][]byte{}
	for _, entry := range entries {
		n := entry.Name()
		if strings.HasSuffix(n, ".backup") || strings.HasSuffix(n, ".no_backup") {
			return nil, errors.New("network statistics transaction in progress")
		}
		if !netstatsFileRE.MatchString(n) {
			continue
		}
		info, e := entry.Info()
		if e != nil {
			return nil, e
		}
		if !info.Mode().IsRegular() || info.Size() > 16*1024*1024 {
			return nil, errors.New("unexpected network history file")
		}
		b, e := os.ReadFile(filepath.Join(dir, n))
		if e != nil {
			return nil, e
		}
		files[n] = b
	}
	if len(files) == 0 {
		return nil, errors.New("no UID history files")
	}
	return files, nil
}
func statsNames(files map[string][]byte) []string {
	names := make([]string, 0, len(files))
	for n := range files {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}
func statsSave(path string, b []byte) error {
	f, e := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	_, e = f.Write(b)
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e == nil {
		e = ce
	}
	if e != nil {
		return e
	}
	read, e := os.ReadFile(path)
	if e != nil {
		return e
	}
	if !bytes.Equal(read, b) {
		return errors.New("temporary history readback mismatch")
	}
	return nil
}
func statsReplace(p *statsPause, name string, b []byte) error {
	if !netstatsFileRE.MatchString(name) {
		return errors.New("invalid history filename")
	}
	if e := p.check(); e != nil {
		return e
	}
	target := filepath.Join(netstatsDir, name)
	info, e := os.Lstat(target)
	if e != nil {
		return e
	}
	if !info.Mode().IsRegular() {
		return errors.New("history target not regular")
	}
	meta, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return errors.New("history ownership unavailable")
	}
	temp := filepath.Join(netstatsDir, fmt.Sprintf(".aw-user11-%d-%s", os.Getpid(), name))
	defer os.Remove(temp)
	if e = statsSave(temp, b); e != nil {
		return e
	}
	if e = os.Chown(temp, int(meta.Uid), int(meta.Gid)); e != nil {
		return e
	}
	if e = os.Chmod(temp, info.Mode().Perm()); e != nil {
		return e
	}
	if _, e = statsCommand(time.Second, "restorecon", temp); e != nil {
		return e
	}
	if e = p.check(); e != nil {
		return e
	}
	return os.Rename(temp, target)
}
func statsSyncDir() error {
	f, e := os.Open(netstatsDir)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}
func statsReload(pid int) error {
	if _, e := statsProcessStart(pid); e != nil {
		return e
	}
	if e := syscall.Kill(pid, syscall.SIGUSR1); e != nil {
		return e
	}
	time.Sleep(time.Second)
	return nil
}
func statsRollback(pid int, before map[string][]byte, committed []string) error {
	if e := statsPersist(); e != nil {
		return e
	}
	p, e := statsFreeze(pid)
	if e != nil {
		return e
	}
	defer p.resume()
	current, e := statsSnapshot(netstatsDir)
	if e != nil {
		return e
	}
	for _, oldName := range committed {
		prefix := oldName[:strings.IndexByte(oldName, '-')+1]
		name := ""
		for n := range current {
			if strings.HasPrefix(n, prefix) {
				if name != "" {
					return errors.New("ambiguous rotated rollback file")
				}
				name = n
			}
		}
		if name == "" {
			return errors.New("rollback history rotated away")
		}
		b, e := statsMergeTarget(before[oldName], current[name])
		if e != nil {
			return e
		}
		if e = statsReplace(p, name, b); e != nil {
			return e
		}
	}
	if e = statsSyncDir(); e != nil {
		return e
	}
	p.resume()
	return statsReload(pid)
}
func netstatsClear(preview bool) (result statsResult, err error) {
	result.Scope = "users10-11-and-removed"
	err = withAuxiliaryLock("user11-netstats", func() (err error) {
		model, e := statsCommand(time.Second, "getprop", "ro.product.model")
		if e != nil {
			return e
		}
		sdk, e := statsCommand(time.Second, "getprop", "ro.build.version.sdk")
		if e != nil {
			return e
		}
		if strings.TrimSpace(model) != "PLK110" || strings.TrimSpace(sdk) != "36" {
			return errors.New("unsupported device or Android version")
		}
		result.Before, e = statsPrepareSelection()
		if e != nil {
			return e
		}
		if !preview {
			if _, e = statsCommand(3*time.Second, "am", "force-stop", "--user", "0", trafficPackage); e != nil {
				return e
			}
		}
		if e = statsPersist(); e != nil {
			return e
		}
		pidText, e := statsCommand(time.Second, "pidof", "system_server")
		if e != nil {
			return e
		}
		pid, e := strconv.Atoi(strings.TrimSpace(pidText))
		if e != nil {
			return errors.New("unexpected system process PID")
		}
		for uid := range statsDeletedUIDs {
			result.DeletedUIDs = append(result.DeletedUIDs, uid)
		}
		sort.Slice(result.DeletedUIDs, func(i, j int) bool { return result.DeletedUIDs[i] < result.DeletedUIDs[j] })
		var pause *statsPause
		if !preview {
			pause, e = statsFreeze(pid)
			if e != nil {
				return e
			}
			defer pause.resume()
		}
		before, e := statsSnapshot(netstatsDir)
		if e != nil {
			return e
		}
		filtered := map[string][]byte{}
		for _, name := range statsNames(before) {
			if pause != nil {
				if e = pause.check(); e != nil {
					return e
				}
			}
			b, _, changed, e := statsFilter(before[name], strings.HasPrefix(name, "uid_tag."))
			if e != nil {
				return e
			}
			result.Changed += changed
			filtered[name] = b
		}
		if preview {
			result.After = statsTotals{}
			return nil
		}
		committed := []string{}
		defer func() {
			if err == nil || len(committed) == 0 {
				return
			}
			var recovery error
			if !pause.resumed && pause.check() == nil {
				for _, name := range committed {
					if e := statsReplace(pause, name, before[name]); e != nil {
						recovery = e
						break
					}
				}
				if recovery == nil {
					recovery = statsSyncDir()
				}
				pause.resume()
			} else {
				pause.resume()
				recovery = statsRollback(pid, before, committed)
			}
			if recovery != nil {
				err = fmt.Errorf("%w; incomplete cleanup recovery: %v", err, recovery)
			} else {
				err = fmt.Errorf("%w; interrupted operation reverted", err)
			}
		}()
		for _, name := range statsNames(filtered) {
			if bytes.Equal(filtered[name], before[name]) {
				continue
			}
			if e = statsReplace(pause, name, filtered[name]); e != nil {
				return e
			}
			committed = append(committed, name)
		}
		if e = statsSyncDir(); e != nil {
			return e
		}
		if e = pause.check(); e != nil {
			return e
		}
		pause.resume()
		if e = statsReload(pid); e != nil {
			return e
		}
		result.After, e = statsReadLive()
		if e != nil {
			return e
		}
		if result.After != (statsTotals{}) {
			return errors.New("live history did not confirm zero; new traffic or retained statistics session")
		}
		if e = statsPersist(); e != nil {
			return e
		}
		result.After, e = statsReadLive()
		if e != nil {
			return e
		}
		if result.After != (statsTotals{}) {
			return errors.New("new traffic accrued during verification")
		}
		logEvent("traffic-history-clear", "users10-11-and-removed")
		return nil
	})
	return result, err
}
