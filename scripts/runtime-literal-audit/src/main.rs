use proc_macro2::{TokenStream, TokenTree};
use serde_json::{Value, json};
use std::{env, fs};

fn collect(tokens: TokenStream, source: &str, entries: &mut Vec<Value>) {
    for token in tokens {
        match token {
            TokenTree::Group(group) => collect(group.stream(), source, entries),
            TokenTree::Literal(literal) => {
                let value = match syn::parse2::<syn::Lit>(TokenTree::Literal(literal.clone()).into()) {
                    Ok(syn::Lit::Str(value)) => Some(value.value()),
                    Ok(syn::Lit::ByteStr(value)) => String::from_utf8(value.value()).ok(),
                    Ok(syn::Lit::CStr(value)) => value.value().to_str().ok().map(str::to_owned),
                    _ => None,
                };
                if let Some(value) = value {
                    let lower = value.to_lowercase();
                    if !lower.contains("ksu") && !lower.contains("kernelsu") { continue; }
                    let range = literal.span().byte_range();
                    let text = source.get(range.clone()).unwrap_or("");
                    entries.push(json!({"value": value, "start": range.start, "end": range.end,
                        "token": literal.to_string(), "source": text, "line": literal.span().start().line}));
                }
            }
            _ => (),
        }
    }
}

fn normalized(tokens: TokenStream) -> String {
    let mut result = String::new();
    for token in tokens {
        match token {
            TokenTree::Group(group) => result.push_str(&format!("{:?}{{{}}}", group.delimiter(), normalized(group.stream()))),
            TokenTree::Literal(literal) => {
                let string = matches!(syn::parse2::<syn::Lit>(TokenTree::Literal(literal.clone()).into()),
                    Ok(syn::Lit::Str(_)) | Ok(syn::Lit::ByteStr(_)) | Ok(syn::Lit::CStr(_)));
                if string { result.push_str("STRING"); }
                else { result.push_str(&literal.to_string()); }
            }
            other => result.push_str(&other.to_string()),
        }
        result.push(' ');
    }
    result
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let source = fs::read_to_string(&args[2]).unwrap();
    let tokens: TokenStream = source.parse().unwrap();
    if args[1] == "list" {
        let mut entries = Vec::new();
        collect(tokens, &source, &mut entries);
        println!("{}", json!(entries));
    } else {
        let after: TokenStream = fs::read_to_string(&args[3]).unwrap().parse().unwrap();
        assert_eq!(normalized(tokens), normalized(after), "Changed non-string runtime tokens");
    }
}
