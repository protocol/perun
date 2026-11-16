package bench

import "os/exec"

func Ping(input string) error {
	return exec.Command("sh", "-c", "ping -c 1 "+input).Run()
}
