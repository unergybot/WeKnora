package main

import (
	"encoding/json"
	"fmt"
)

type GrepChunksInput struct {
	Pattern []string `json:"pattern"`
}

func main() {
	// Case 1: Array of strings (Correct)
	json1 := `{"pattern": ["test"]}`
	var input1 GrepChunksInput
	err1 := json.Unmarshal([]byte(json1), &input1)
	fmt.Printf("Case 1 (Array): Error=%v, Value=%v\n", err1, input1)

	// Case 2: Single string (Likely Incorrect)
	json2 := `{"pattern": "test"}`
	var input2 GrepChunksInput
	err2 := json.Unmarshal([]byte(json2), &input2)
	fmt.Printf("Case 2 (String): Error=%v, Value=%v\n", err2, input2)
}
