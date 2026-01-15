# Auto-Discovery Knowledge Graph Design

**Date:** 2026-01-14
**Status:** Ready for Implementation
**Author:** Claude + User collaboration

## Overview

Add automatic entity-relation extraction to WeKnora's Knowledge Graph feature, eliminating the need for users to manually define a schema before extraction.

### Current Behavior
- User must define: sample text, tags (relationship types), nodes (entities), relations
- System extracts only entities/relations matching the predefined schema
- Error "text cannot be empty" if knowledge graph enabled without schema

### Proposed Behavior
- User enables "Auto Discovery" mode
- Documents are uploaded normally
- Background job extracts all entities and relationships automatically
- User can browse, query, and merge entities post-extraction

## User Experience

### Creating a Knowledge Base with Auto-Discovery

1. Create new knowledge base
2. Navigate to "Graph" settings tab
3. Enable "Knowledge Graph"
4. Select "Auto Discovery" mode (new option)
5. Upload documents as usual
6. Graph builds automatically in background

### Querying the Graph

Two interfaces provided:

1. **Natural Language Query** - Ask questions like "What suppliers are connected to Product X?"
2. **Visual Graph Explorer** - Interactive node-and-edge visualization with click-to-expand

### Entity Management

- View all extracted entities with mention counts
- System suggests similar entities for merging (e.g., "Microsoft", "Microsoft Corp", "MSFT")
- Manual merge UI allows user to combine entities on demand

## Technical Design

### Data Model

#### Entity Structure
```go
type AutoExtractedEntity struct {
    ID            string            `json:"id"`
    Name          string            `json:"name"`           // As extracted
    Type          string            `json:"type"`           // LLM-determined (Person, Organization, Product, etc.)
    CanonicalID   *string           `json:"canonical_id"`   // Set when merged into another entity
    SourceChunks  []string          `json:"source_chunks"`  // Chunk IDs for traceability
    Confidence    float64           `json:"confidence"`     // LLM confidence score
    Attributes    map[string]string `json:"attributes"`     // Optional properties
    KnowledgeBase string            `json:"knowledge_base_id"`
    CreatedAt     time.Time         `json:"created_at"`
}
```

#### Relationship Structure
```go
type AutoExtractedRelation struct {
    ID           string    `json:"id"`
    FromEntity   string    `json:"from_entity_id"`
    ToEntity     string    `json:"to_entity_id"`
    Type         string    `json:"type"`           // LLM-determined relationship type
    SourceChunks []string  `json:"source_chunks"`
    Confidence   float64   `json:"confidence"`
    KnowledgeBase string   `json:"knowledge_base_id"`
    CreatedAt    time.Time `json:"created_at"`
}
```

### Configuration Changes

```go
// Modified ExtractConfig in internal/types/graph.go
type ExtractConfig struct {
    Enabled  bool `json:"enabled"`
    AutoMode bool `json:"auto_mode"` // NEW: enables schema-free extraction

    // Below fields only used when AutoMode=false
    Text      string     `json:"text,omitempty"`
    Tags      []string   `json:"tags,omitempty"`
    Nodes     []Node     `json:"nodes,omitempty"`
    Relations []Relation `json:"relations,omitempty"`
}
```

### Processing Pipeline

```
Document Upload
     ↓
Chunking & Embedding (existing)
     ↓
Queue extraction job (new) ──→ Asynq background worker
                                      ↓
                              For each chunk:
                                - LLM extracts entities/relations
                                - Store in Neo4j
                                - Update progress in Redis
                                      ↓
                              Mark KB graph as "ready"
```

### New Backend Components

| Component | File | Purpose |
|-----------|------|---------|
| `AutoExtractConfig` | `internal/types/graph.go` | Configuration for auto mode |
| `AutoExtractedEntity` | `internal/types/graph.go` | Entity data structure |
| `AutoExtractedRelation` | `internal/types/graph.go` | Relationship data structure |
| `TypeAutoEntityExtract` | `internal/types/task.go` | Asynq task type constant |
| `AutoEntityExtractPayload` | `internal/types/task.go` | Task payload structure |
| `AutoEntityExtractHandler` | `internal/worker/auto_extract.go` | Asynq job handler |
| `GraphAutoExtractor` | `internal/application/service/graph_auto.go` | LLM extraction logic |
| `EntityMergeService` | `internal/application/service/entity_merge.go` | Entity deduplication |

### New API Endpoints

```
POST   /api/v1/knowledge-bases/{id}/graph/extract     - Trigger extraction
GET    /api/v1/knowledge-bases/{id}/graph/status      - Get extraction progress
GET    /api/v1/knowledge-bases/{id}/graph/entities    - List entities (paginated)
GET    /api/v1/knowledge-bases/{id}/graph/entities/{eid}/neighbors - Get connected entities
POST   /api/v1/knowledge-bases/{id}/graph/entities/merge - Merge entities
GET    /api/v1/knowledge-bases/{id}/graph/query       - Natural language graph query
GET    /api/v1/knowledge-bases/{id}/graph/similar     - Get similar entity suggestions
```

### LLM Extraction Prompt

```
You are an entity and relationship extraction system. Extract all entities and relationships from the following text.

Entity types to consider: Person, Organization, Product, Location, Date, Event, Concept, Document, Technology, or any other relevant type.

For each entity, provide:
- name: The entity name as it appears in the text
- type: The entity type
- attributes: Any additional properties mentioned
- confidence: Your confidence score (0.0-1.0)

For each relationship, provide:
- from_entity: Source entity name
- to_entity: Target entity name
- type: Relationship type (e.g., "works_for", "supplies", "located_in", "created_by")
- confidence: Your confidence score (0.0-1.0)

Text:
"""
{chunk_text}
"""

Return valid JSON:
{
  "entities": [
    {"name": "...", "type": "...", "attributes": {...}, "confidence": 0.95}
  ],
  "relationships": [
    {"from_entity": "...", "to_entity": "...", "type": "...", "confidence": 0.87}
  ]
}
```

### Frontend Changes

#### Modified: GraphSettings.vue

Add mode selection toggle:
- "Auto Discovery" - LLM automatically extracts (hides schema fields)
- "Manual Schema" - Current behavior (shows all schema fields)

#### New: GraphProgress.vue

Progress indicator component showing:
- Extraction progress percentage
- Documents processed / total
- Entities found count
- Relationships found count

#### New: EntityBrowser.vue

Entity management interface:
- Search/filter entities
- View entity details and sources
- Similar entity suggestions
- Merge UI for combining duplicates

#### New: GraphExplorer.vue

Interactive graph visualization:
- D3.js or vis.js based
- Click node to expand neighbors
- Drag to rearrange
- Zoom/pan controls
- Export options

#### New: GraphQuery.vue

Natural language query interface:
- Text input for questions
- Results show matching entities/paths
- Source document links

### Neo4j Schema

```cypher
// Entity nodes
CREATE (e:Entity {
  id: $id,
  name: $name,
  type: $type,
  canonical_id: $canonical_id,
  confidence: $confidence,
  knowledge_base_id: $kb_id,
  created_at: datetime()
})

// Relationship edges (dynamic type)
MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})
CREATE (a)-[r:RELATES_TO {
  id: $rel_id,
  type: $rel_type,
  confidence: $confidence,
  source_chunks: $chunks
}]->(b)

// Index for fast lookups
CREATE INDEX entity_kb_idx FOR (e:Entity) ON (e.knowledge_base_id)
CREATE INDEX entity_name_idx FOR (e:Entity) ON (e.name)
```

### Redis Keys for Progress

```
kb:{kb_id}:auto_extract:status     - "pending" | "processing" | "completed" | "failed"
kb:{kb_id}:auto_extract:progress   - JSON {total: N, processed: N, entities: N, relations: N}
kb:{kb_id}:auto_extract:error      - Error message if failed
```

## Validation Changes

Modify `validateExtractConfig` in `internal/handler/knowledgebase.go`:

```go
func validateExtractConfig(config *ExtractConfig) error {
    if config == nil || !config.Enabled {
        return nil
    }

    // Auto mode requires no manual schema
    if config.AutoMode {
        return nil  // No validation needed for auto mode
    }

    // Manual mode validation (existing logic)
    if config.Text == "" {
        return errors.NewBadRequestError("text cannot be empty")
    }
    // ... rest of existing validation
}
```

## Implementation Phases

### Phase 1: Backend Foundation
- Add `AutoMode` to `ExtractConfig`
- Update validation to skip schema checks for auto mode
- Create auto extraction worker skeleton
- Add progress tracking in Redis

### Phase 2: LLM Extraction
- Implement `GraphAutoExtractor` service
- Create extraction prompt
- Store entities/relations in Neo4j
- Handle extraction errors gracefully

### Phase 3: API Endpoints
- Entity listing endpoint
- Graph query endpoint (NL → Cypher)
- Entity merge endpoint
- Similar entities endpoint

### Phase 4: Frontend - Settings & Progress
- Add Auto/Manual toggle to GraphSettings.vue
- Add extraction progress indicator
- Update form validation

### Phase 5: Frontend - Entity Browser
- Entity list view with search/filter
- Entity detail view
- Similar entity suggestions
- Merge UI

### Phase 6: Frontend - Graph Explorer
- Interactive graph visualization
- Node expansion
- Natural language query interface

## Testing Strategy

- Unit tests for extraction prompt parsing
- Integration tests for Neo4j operations
- E2E tests for full extraction pipeline
- UI component tests for new Vue components

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM extraction inconsistency | Confidence thresholds, source tracking |
| Neo4j performance at scale | Proper indexing, pagination |
| Entity explosion (too many) | Configurable confidence threshold |
| Background job failures | Retry logic, error reporting |

## Future Enhancements

- Automatic entity merging based on embedding similarity
- Scheduled re-extraction when documents updated
- Export graph to RDF/OWL formats
- Graph-enhanced RAG retrieval
