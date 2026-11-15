resource "aws_s3_bucket" "assets" {
  bucket = "acme-bench-assets"
  acl    = "public-read"
}
