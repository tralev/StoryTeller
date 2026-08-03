# StoryTeller — API Reference

## Model Interfaces

The Forge never references specific models. All pipeline code depends on these interfaces. Concrete implementations are resolved from `config/models.yaml`.

---

### TextGenerator

Generates structured text output from prompts. Used for: World Bible, Style Bible, Story, Decision Points, Graph Skeleton, Node Text, Image Prompts, ABC Notation.

```python
class TextGenerator(Protocol):
    """Generates structured text from prompt templates."""

    provider: str          # e.g., "llama_cpp"
    model_name: str        # e.g., "qwen2.5-7b-instruct"
    quantization: str      # e.g., "Q4_K_M"

    async def generate(
        self,
        prompt: str,
        schema: dict | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Generate structured output from a prompt.

        Args:
            prompt: The formatted prompt string (from Jinja2 template).
            schema: Optional JSON Schema the output must conform to.
            temperature: Sampling temperature (0.0 = deterministic).
            seed: RNG seed for reproducibility.
            max_tokens: Maximum tokens to generate.

        Returns:
            Parsed JSON dict matching the schema.

        Raises:
            GenerationError: If generation fails or output doesn't match schema.
        """
        ...

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Generate text with token-by-token streaming.

        Used for Game Master responses on mobile.

        Yields:
            Individual tokens as they are generated.
        """
        ...

    async def load(self) -> None:
        """Load the model into memory."""
        ...

    async def unload(self) -> None:
        """Unload the model to free RAM."""
        ...

    @property
    def ram_usage_mb(self) -> int:
        """Estimated RAM usage in MB."""
        ...
```

---

### Validator

Validates generated content against rules, schemas, and cross-references. Uses a different model than the generator for independent critique.

```python
class Validator(Protocol):
    """Validates generated content against rules and schemas."""

    provider: str
    model_name: str
    quantization: str

    async def validate(
        self,
        content: dict,
        context: ValidationContext,
    ) -> ValidationResult:
        """
        Validate content against its schema and business rules.

        Args:
            content: The generated content to validate.
            context: Validation context including:
                - schema: JSON Schema to validate against
                - bible: World Bible for cross-reference checking
                - story: Story text for consistency checking
                - graph: Graph for topology validation
                - previous_outputs: Outputs from prior steps

        Returns:
            ValidationResult with is_valid flag and error details.
        """
        ...

    async def consistency_check(
        self,
        text: str,
        bible: dict,
    ) -> ConsistencyReport:
        """
        Check if text contradicts the World Bible.

        Returns:
            ConsistencyReport with list of violations and suggestions.
        """
        ...

    async def load(self) -> None: ...
    async def unload(self) -> None: ...
```

---

### ImageGenerator

Generates images from text prompts. Prompts include the Style Bible suffix appended by the pipeline.

```python
class ImageGenerator(Protocol):
    """Generates images from text prompts."""

    provider: str
    model_name: str
    quantization: str

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        """
        Generate an image from a text prompt.

        Args:
            prompt: The image generation prompt.
            negative_prompt: What to avoid in the image.
            size: Output dimensions (width, height).
            seed: RNG seed for reproducibility.
            steps: Diffusion steps (more = higher quality, slower).

        Returns:
            Raw PNG image bytes.
        """
        ...

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        """Generate a thumbnail from a full-size image."""
        ...

    async def load(self) -> None: ...
    async def unload(self) -> None: ...
```

---

### MusicGenerator

Generates ABC music notation from scene descriptions. The pipeline converts ABC to MIDI via music21.

```python
class MusicGenerator(Protocol):
    """Generates ABC music notation from scene descriptions."""

    provider: str    # e.g., "abc_notation" (LLM generates ABC as text)

    async def generate(
        self,
        scene_text: str,
        mood: str,
        seed: int | None = None,
    ) -> str:
        """
        Generate ABC notation for a scene.

        Args:
            scene_text: The text of the scene.
            mood: The emotional tone (e.g., "tense", "peaceful", "triumphant").
            seed: RNG seed for reproducibility.

        Returns:
            Raw ABC notation string starting with "X:1".
        """
        ...

    @staticmethod
    def abc_to_midi(abc_notation: str) -> bytes:
        """
        Convert ABC notation to MIDI bytes.

        Uses music21 for conversion. No LLM involved.
        """
        ...

    @staticmethod
    def validate_abc(abc_notation: str) -> bool:
        """Check if ABC notation is syntactically valid."""
        ...
```

---

### GameMaster

Answers reader questions with context-aware responses. Runs on mobile via llama.cpp.

```python
class GameMaster(Protocol):
    """Answers reader questions about the story world."""

    provider: str
    model_name: str
    quantization: str

    async def answer(
        self,
        question: str,
        context: GameMasterContext,
    ) -> AsyncIterator[str]:
        """
        Answer a reader's question, streaming the response.

        Args:
            question: The reader's question.
            context: Assembled context including:
                - current_scene: Text of the current node
                - relevant_lore: Entity summaries from gm_index lookup
                - world_rules: Key rules from the Bible

        Yields:
            Response tokens as they are generated.
        """
        ...

    async def load(self) -> None: ...
    async def unload(self) -> None: ...
```

---

## Pipeline Job

A unit of work in the Job Queue.

```python
@dataclass
class Job:
    job_id: str
    job_type: JobType          # e.g., GENERATE_BIBLE, GENERATE_NODE, GENERATE_IMAGE
    generator: TextGenerator | ImageGenerator | MusicGenerator
    validator: Validator
    prompt: str
    schema: dict | None
    context: PipelineContext
    seed: int
    max_retries: int = 3
    dependencies: list[str] = field(default_factory=list)  # Job IDs that must complete first
```

---

## Pipeline Context

Passed through every pipeline step. Accumulates outputs and state.

```python
@dataclass
class PipelineContext:
    run_id: str
    seed: int
    config: dict                    # Full config/models.yaml
    outputs: dict[str, Any]         # Outputs from completed steps
    feedback: list[str]             # Accumulated validation errors for retry
    state: PipelineState            # Current step, status
    checkpoint: CheckpointManager
```

---

## Validation Result

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retry_prompt: str | None = None  # Feedback to inject into next generation attempt
```

---

## Normalizer

Enforces project-wide conventions on all output before commit.

```python
class Normalizer:
    """Enforces conventions: IDs, naming, sorting, formatting."""

    @staticmethod
    def normalize_entity_ids(data: dict) -> dict: ...
    
    @staticmethod
    def normalize_names(data: dict) -> dict: ...
    
    @staticmethod
    def sort_arrays(data: dict) -> dict: ...
    
    @staticmethod
    def normalize_whitespace(text: str) -> str: ...
    
    @staticmethod
    def normalize_json(data: dict) -> str:
        """Serialize with sorted keys, 2-space indent, 6-decimal floats."""
        return json.dumps(data, sort_keys=True, indent=2, 
                         default=_float_handler)
    
    @staticmethod
    def normalize_paths(data: dict) -> dict: ...
    
    @staticmethod
    def normalize_flag_names(data: dict) -> dict: ...
    
    @staticmethod
    def process(data: dict, schema_name: str) -> dict:
        """Run all normalization passes."""
        ...
```

---

## Configuration (config/models.yaml)

```yaml
# Model interface → concrete implementation mapping
# Change models here — no code changes needed.

generators:
  text:
    provider: llama_cpp
    model: qwen2.5-7b-instruct
    quantization: Q4_K_M
    max_tokens: 4096
    temperature: 0.7

  validator:
    provider: llama_cpp
    model: phi-3.5-mini-instruct
    quantization: Q4_K_M
    max_tokens: 2048
    temperature: 0.3  # Lower temperature for more consistent validation

  image:
    provider: stable_diffusion_cpp
    model: sdxl-turbo
    quantization: Q8_0
    size: [512, 512]
    steps: 20

  music:
    provider: abc_notation    # LLM generates ABC; music21 converts to MIDI
    model: qwen2.5-7b-instruct  # Uses same text generator

  game_master:
    provider: llama_cpp
    model: llama-3.2-3b-instruct
    quantization: Q4_K_M
    max_tokens: 256
    temperature: 0.8  # Slightly creative for in-character responses

# Worker configuration
pipeline:
  workers: 4                # Number of parallel workers (default: CPU cores - 1)
  max_retries: 3            # Max retries per job on validation failure
  checkpoint_interval: 1    # Save checkpoint after every N completed jobs

# RAM budget (MB)
limits:
  max_ram_mb: 10240         # 10 GB
  model_unload_threshold: 0.9  # Unload models when 90% RAM used
```

---

## CLI Reference

```
Usage: forge [COMMAND] [OPTIONS]

Commands:
  generate          Run the full pipeline
  generate-bible    Generate World Bible only
  generate-story    Generate linear story from Bible
  generate-graph    Generate CYOA graph from story
  generate-assets   Generate images and MIDI from graph
  package           Package output directory into .story
  resume            Resume from last checkpoint
  validate          Validate a .story file
  verify            Verify determinism (SHA256 match)
  download-models   Download required models from Hugging Face
  config            Show or set configuration

Options:
  --title TEXT          Story title
  --tone TEXT           Story tone (dark_fantasy, heroic_fantasy, grimdark, mythic)
  --seed INTEGER        RNG seed for reproducibility
  --output DIR          Output directory
  --workers INTEGER     Number of parallel workers
  --max-ram INTEGER     RAM limit in GB
  --help                Show help
```

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture using these interfaces
- **[schemas/](schemas/)** — JSON Schema contracts validated by these interfaces
- **[design.md](design.md)** — Behavioral design showing where each interface is used
