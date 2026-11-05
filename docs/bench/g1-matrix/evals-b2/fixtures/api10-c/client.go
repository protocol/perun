package main

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

var httpClient = &http.Client{
	Timeout: 6 * time.Second,
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	},
}

const feedBase = "https://feed.provider.example.com/v1/stations"

func openStation(id string) (io.ReadCloser, error) {
	resp, err := httpClient.Get(feedBase + "/" + url.PathEscape(id) + "/latest")
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("feed status %d", resp.StatusCode)
	}
	return resp.Body, nil
}
