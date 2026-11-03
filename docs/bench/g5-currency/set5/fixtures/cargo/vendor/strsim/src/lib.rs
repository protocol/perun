//! Vendored copy of upstream strsim 0.10.0 (MIT), do not edit.
pub fn hamming(a: &str, b: &str) -> usize { a.chars().zip(b.chars()).filter(|(x, y)| x != y).count() }
