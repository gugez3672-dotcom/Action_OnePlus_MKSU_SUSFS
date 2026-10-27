package main

// Standalone DailyNotes tool. It has no dependency on the AmbientWorkspace module.
import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"syscall"
)

const trafficPackage = "com.oplus.trafficmonitor"

var userIDPattern = regexp.MustCompile(`UserInfo\{([0-9]+):`)

func short(s string) string {
	if len(s) > 400 {
		return s[:400]
	}
	return s
}

func withAuxiliaryLock(_ string, action func() error) error {
	lockPath := os.Getenv("DN_NETSTATS_LOCK_FILE")
	if !filepath.IsAbs(lockPath) || filepath.Base(lockPath) != "netstats.lock" {
		return errors.New("private network statistics lock path missing")
	}
	file, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer file.Close()
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return fmt.Errorf("network statistics operation busy: %w", err)
	}
	defer syscall.Flock(int(file.Fd()), syscall.LOCK_UN)
	return action()
}

func logEvent(event, detail string) { fmt.Fprintln(os.Stderr, event, detail) }

func main() {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "root required")
		os.Exit(1)
	}
	if len(os.Args) == 4 && os.Args[1] == "netstats-guard" {
		if err := netstatsGuard(os.Args[2:]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	if len(os.Args) != 2 || (os.Args[1] != "preview" && os.Args[1] != "clear") {
		fmt.Fprintln(os.Stderr, "usage: dn-netstats preview|clear")
		os.Exit(2)
	}
	result, err := netstatsClear(os.Args[1] == "preview")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err = json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, errors.New("result serialization failed"))
		os.Exit(1)
	}
}
