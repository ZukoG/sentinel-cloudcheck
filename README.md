# sentinel-cloudcheck

A small serverless tool on AWS that grades a website's HTTP security
headers. Send it a URL, an AWS Lambda function fetches that page once
(passive, read-only), scores six security headers, stores the result in
DynamoDB, and returns the grade as JSON. The whole stack is defined in
Terraform and can be created and destroyed with one command each.

Built for a Cloud Computing elective, as a companion to
[sentinel-secscan](https://github.com/ZukoG/sentinel-secscan).

> Under construction. Full setup and usage instructions land on Day 4.

## Documentation

- [Software Requirements Specification](docs/SRS.md)

## License

[MIT](LICENSE)
