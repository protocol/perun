package bench

import "os/exec"

func Ping(host string) error {
	return exec.Command("/sbin/ping", "-c", "1", host).Run()
}
