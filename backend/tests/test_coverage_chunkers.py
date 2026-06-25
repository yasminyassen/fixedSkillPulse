"""Tests for code chunkers."""

from ai_services.requirements.coverage.chunkers import _get_treesitter_parser, chunk_python, chunk_source_file


def test_python_function_chunk():
    source = '''
def hello():
    return "world"

class Greeter:
    def greet(self):
        return "hi"
'''
    chunks = chunk_python(source, "app/greet.py")
    assert len(chunks) >= 2
    names = {c.symbol_name for c in chunks}
    assert "hello" in names
    assert "Greeter" in names


def test_semantic_fallback_on_bad_python():
    chunks = chunk_python("def broken(", "bad.py")
    assert len(chunks) >= 1
    assert chunks[0].symbol_type == "semantic"


def test_js_extension_routes_to_treesitter_symbol_chunk():
    source = "export function add(a, b) { return a + b; }\n"
    chunks = chunk_source_file("src/math.js", source)
    assert len(chunks) >= 1
    assert chunks[0].language == "javascript"
    assert chunks[0].symbol_type == "function_declaration"
    assert chunks[0].symbol_name == "add"


def test_frontend_extensions_use_treesitter_symbol_chunks():
    fixtures = [
        ("src/App.jsx", "export function App() { return <div>Hello</div>; }\n", "javascript", "App"),
        ("src/math.ts", "export function add(a: number, b: number): number { return a + b; }\n", "typescript", "add"),
        ("src/App.tsx", "type Props = { name: string };\nexport function App({ name }: Props) { return <div>{name}</div>; }\n", "tsx", "App"),
        ("src/Card.tsx", "export const Card = () => <section>Card</section>;\n", "tsx", "Card"),
    ]
    for path, source, language, symbol_name in fixtures:
        chunks = chunk_source_file(path, source)
        assert chunks
        assert any(chunk.language == language and chunk.symbol_name == symbol_name and chunk.symbol_type != "semantic" for chunk in chunks)


def test_dedicated_javascript_and_typescript_parsers_load():
    for language in ["javascript", "typescript", "tsx"]:
        parser, lang = _get_treesitter_parser(language)
        assert parser is not None
        assert lang is not None
