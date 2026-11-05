package main

import (
	"encoding/json"
	"errors"
	"io"
)

type Reading struct {
	Station string  `json:"station"`
	TempC   float64 `json:"temp_c"`
	Wind    float64 `json:"wind_kph"`
}

func readStation(body io.ReadCloser) (*Reading, error) {
	defer body.Close()
	raw, err := io.ReadAll(body)
	if err != nil {
		return nil, err
	}
	var r Reading
	if err := json.Unmarshal(raw, &r); err != nil {
		return nil, err
	}
	if r.Station == "" || r.TempC < -90 || r.TempC > 60 || r.Wind < 0 || r.Wind > 400 {
		return nil, errors.New("reading out of range")
	}
	return &r, nil
}
