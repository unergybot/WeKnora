package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

var readDocumentSectionTool = BaseTool{
	name: ToolReadDocumentSection,
	description: `Read specific sections or pages of a document to find detailed information.

## When to Use

Use this tool when:
- You need to find specific data within a document (e.g., revenue figures, dates, names)
- Semantic search didn't return the exact information needed
- You need to read through tables in the document
- The user asks about specific content that requires reading document sections

Do NOT use when:
- You already have the answer from knowledge_search results
- The query is general and doesn't need specific document reading

## Input Modes

- **raw**: Returns plain text from the specified page range
- **structured**: Parses content into headings, paragraphs, and tables for easier analysis

## Output

Returns document content from the specified section with clear markers for document structure.
Use page navigation (start_chunk, end_chunk) to browse through large documents.`,
	schema: json.RawMessage(`{
  "type": "object",
  "properties": {
    "knowledge_id": {
      "type": "string",
      "description": "The document/knowledge ID to read from (obtained from search results or document info)"
    },
    "mode": {
      "type": "string",
      "enum": ["raw", "structured"],
      "description": "Output mode: 'raw' for plain text, 'structured' for parsed headings/tables/paragraphs",
      "default": "raw"
    },
    "start_chunk": {
      "type": "integer",
      "description": "Starting chunk index (0-based, default 0)",
      "default": 0,
      "minimum": 0
    },
    "end_chunk": {
      "type": "integer",
      "description": "Ending chunk index (inclusive, default: start_chunk + 10)",
      "minimum": 0
    },
    "section_filter": {
      "type": "string",
      "description": "Optional keyword to filter sections (only returns chunks containing this keyword)"
    }
  },
  "required": ["knowledge_id"]
}`),
}

// ReadDocumentSectionInput defines the input parameters
type ReadDocumentSectionInput struct {
	KnowledgeID   string `json:"knowledge_id"`
	Mode          string `json:"mode"`
	StartChunk    int    `json:"start_chunk"`
	EndChunk      int    `json:"end_chunk"`
	SectionFilter string `json:"section_filter"`
}

// ReadDocumentSectionTool reads specific sections of a document
type ReadDocumentSectionTool struct {
	BaseTool
	knowledgeService interfaces.KnowledgeService
	chunkService     interfaces.ChunkService
}

// NewReadDocumentSectionTool creates a new read document section tool
func NewReadDocumentSectionTool(
	knowledgeService interfaces.KnowledgeService,
	chunkService interfaces.ChunkService,
) *ReadDocumentSectionTool {
	return &ReadDocumentSectionTool{
		BaseTool:         readDocumentSectionTool,
		knowledgeService: knowledgeService,
		chunkService:     chunkService,
	}
}

// Execute reads document sections
func (t *ReadDocumentSectionTool) Execute(ctx context.Context, args json.RawMessage) (*types.ToolResult, error) {
	tenantID := uint64(0)
	if tid, ok := ctx.Value(types.TenantIDContextKey).(uint64); ok {
		tenantID = tid
	}

	// Parse input
	var input ReadDocumentSectionInput
	if err := json.Unmarshal(args, &input); err != nil {
		return &types.ToolResult{
			Success: false,
			Error:   fmt.Sprintf("Failed to parse arguments: %v", err),
		}, err
	}

	// Validate required fields
	if input.KnowledgeID == "" {
		return &types.ToolResult{
			Success: false,
			Error:   "knowledge_id is required",
		}, fmt.Errorf("knowledge_id is required")
	}

	// Set defaults
	if input.Mode == "" {
		input.Mode = "raw"
	}
	if input.EndChunk == 0 {
		input.EndChunk = input.StartChunk + 10
	}

	// Validate mode
	if input.Mode != "raw" && input.Mode != "structured" {
		return &types.ToolResult{
			Success: false,
			Error:   "mode must be 'raw' or 'structured'",
		}, fmt.Errorf("invalid mode: %s", input.Mode)
	}

	// Get knowledge metadata for title
	knowledge, err := t.knowledgeService.GetRepository().GetKnowledgeByID(ctx, tenantID, input.KnowledgeID)
	if err != nil {
		return &types.ToolResult{
			Success: false,
			Error:   fmt.Sprintf("Document not found: %v", err),
		}, err
	}

	// Calculate page size and fetch chunks
	pageSize := input.EndChunk - input.StartChunk + 1
	if pageSize > 50 {
		pageSize = 50 // Cap at 50 chunks to avoid context overflow
	}
	if pageSize < 1 {
		pageSize = 10
	}

	// Calculate page number (1-indexed for the service)
	page := (input.StartChunk / pageSize) + 1

	// Fetch chunks
	chunks, total, err := t.chunkService.GetRepository().ListPagedChunksByKnowledgeID(
		ctx,
		tenantID,
		input.KnowledgeID,
		&types.Pagination{
			Page:     page,
			PageSize: pageSize,
		},
		[]types.ChunkType{types.ChunkTypeText},
		"", "", "", "", "",
	)
	if err != nil {
		return &types.ToolResult{
			Success: false,
			Error:   fmt.Sprintf("Failed to fetch document chunks: %v", err),
		}, err
	}

	if len(chunks) == 0 {
		return &types.ToolResult{
			Success: true,
			Output:  fmt.Sprintf("No content found in document '%s' for the requested range.", knowledge.Title),
			Data: map[string]interface{}{
				"knowledge_id": input.KnowledgeID,
				"title":        knowledge.Title,
				"total_chunks": total,
			},
		}, nil
	}

	// Sort chunks by index
	sort.Slice(chunks, func(i, j int) bool {
		return chunks[i].ChunkIndex < chunks[j].ChunkIndex
	})

	// Apply section filter if provided
	if input.SectionFilter != "" {
		filteredChunks := make([]*types.Chunk, 0)
		filterLower := strings.ToLower(input.SectionFilter)
		for _, chunk := range chunks {
			if strings.Contains(strings.ToLower(chunk.Content), filterLower) {
				filteredChunks = append(filteredChunks, chunk)
			}
		}
		chunks = filteredChunks
	}

	// Format output based on mode
	var output string
	var structuredData map[string]interface{}

	if input.Mode == "structured" {
		output, structuredData = t.formatStructured(chunks, knowledge.Title, total)
	} else {
		output = t.formatRaw(chunks, knowledge.Title, total)
	}

	result := &types.ToolResult{
		Success: true,
		Output:  output,
		Data: map[string]interface{}{
			"knowledge_id":   input.KnowledgeID,
			"title":          knowledge.Title,
			"total_chunks":   total,
			"returned_count": len(chunks),
			"start_chunk":    input.StartChunk,
			"end_chunk":      input.EndChunk,
			"mode":           input.Mode,
			"display_type":   "document_section",
		},
	}

	if structuredData != nil {
		result.Data["structured"] = structuredData
	}

	return result, nil
}

// formatRaw formats chunks as plain text
func (t *ReadDocumentSectionTool) formatRaw(chunks []*types.Chunk, title string, total int64) string {
	var sb strings.Builder

	sb.WriteString(fmt.Sprintf("=== Document: %s ===\n", title))
	sb.WriteString(fmt.Sprintf("Showing chunks %d-%d of %d total\n\n",
		chunks[0].ChunkIndex,
		chunks[len(chunks)-1].ChunkIndex,
		total))

	for _, chunk := range chunks {
		sb.WriteString(fmt.Sprintf("--- Chunk #%d ---\n", chunk.ChunkIndex))
		sb.WriteString(chunk.Content)
		sb.WriteString("\n\n")
	}

	if int64(chunks[len(chunks)-1].ChunkIndex) < total-1 {
		sb.WriteString(fmt.Sprintf("\n[More content available. Use start_chunk=%d to continue reading]\n",
			chunks[len(chunks)-1].ChunkIndex+1))
	}

	return sb.String()
}

// formatStructured parses and formats chunks with structure
func (t *ReadDocumentSectionTool) formatStructured(chunks []*types.Chunk, title string, total int64) (string, map[string]interface{}) {
	var sb strings.Builder

	headings := make([]map[string]interface{}, 0)
	tables := make([]map[string]interface{}, 0)
	paragraphs := make([]string, 0)

	// Regex patterns
	headingPattern := regexp.MustCompile(`(?m)^(#{1,6})\s+(.+)$`)
	tableRowPattern := regexp.MustCompile(`(?m)^\|.+\|$`)

	sb.WriteString(fmt.Sprintf("=== Document: %s (Structured) ===\n", title))
	sb.WriteString(fmt.Sprintf("Chunks %d-%d of %d\n\n",
		chunks[0].ChunkIndex,
		chunks[len(chunks)-1].ChunkIndex,
		total))

	for _, chunk := range chunks {
		content := chunk.Content

		// Extract headings
		headingMatches := headingPattern.FindAllStringSubmatch(content, -1)
		for _, match := range headingMatches {
			level := len(match[1])
			text := strings.TrimSpace(match[2])
			headings = append(headings, map[string]interface{}{
				"level":       level,
				"text":        text,
				"chunk_index": chunk.ChunkIndex,
			})
			sb.WriteString(fmt.Sprintf("[H%d] %s\n", level, text))
		}

		// Extract tables
		tableLines := tableRowPattern.FindAllString(content, -1)
		if len(tableLines) >= 2 { // At least header + separator or data
			tableContent := strings.Join(tableLines, "\n")
			tables = append(tables, map[string]interface{}{
				"content":     tableContent,
				"row_count":   len(tableLines),
				"chunk_index": chunk.ChunkIndex,
			})
			sb.WriteString("\n[TABLE]\n")
			sb.WriteString(tableContent)
			sb.WriteString("\n[/TABLE]\n\n")
		}

		// Extract non-heading, non-table text as paragraphs
		cleanContent := headingPattern.ReplaceAllString(content, "")
		cleanContent = tableRowPattern.ReplaceAllString(cleanContent, "")
		cleanContent = strings.TrimSpace(cleanContent)
		if cleanContent != "" {
			paragraphs = append(paragraphs, cleanContent)
			sb.WriteString(fmt.Sprintf("[PARA] %s\n\n", truncateString(cleanContent, 200)))
		}
	}

	// Summary
	sb.WriteString(fmt.Sprintf("\n--- Summary ---\n"))
	sb.WriteString(fmt.Sprintf("Headings: %d\n", len(headings)))
	sb.WriteString(fmt.Sprintf("Tables: %d\n", len(tables)))
	sb.WriteString(fmt.Sprintf("Paragraphs: %d\n", len(paragraphs)))

	if int64(chunks[len(chunks)-1].ChunkIndex) < total-1 {
		sb.WriteString(fmt.Sprintf("\n[More content available. Use start_chunk=%d to continue]\n",
			chunks[len(chunks)-1].ChunkIndex+1))
	}

	structuredData := map[string]interface{}{
		"headings":   headings,
		"tables":     tables,
		"paragraphs": paragraphs,
	}

	return sb.String(), structuredData
}

// truncateString truncates a string to maxLen characters
func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
