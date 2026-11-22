package main

import (
	"crypto/md5"
	"os/exec"
)

func main() {
	_ = md5.New()
	_ = exec.Command("sh", "-c", "echo hi").Run()
}
