# Terraform Guide

## Scope

This configuration targets local FakeCloud endpoints on port `4566`; it is not
a production AWS configuration. The checked-in `.terraform.lock.hcl` pins the
provider selection and should be updated only through Terraform commands.

Do not infer or reproduce company production infrastructure from hostnames or
other identifiers in the supplied documents. A production deployment is out of
scope unless the user explicitly authorises a separate, security-reviewed stack.

## Workflow

Run from `backend/terraform/` (with FakeCloud available where required):

```bash
terraform fmt -check
terraform init
terraform validate
terraform plan
```

Review a plan before applying during ordinary development. Do not commit
`.terraform/`, state, plans, or variable files containing secrets.

## Change rules

- Preserve local-only endpoint overrides unless intentionally creating a
  separate production stack.
- Keep resource names, image tags, ports, environment variables, Dockerfile,
  setup script, and architecture documentation aligned.
- Mark sensitive outputs as sensitive and supply secrets through a secret
  mechanism rather than task-definition plaintext for any non-local target.
- Keep synthetic/demo data isolated from company environments. Never configure
  this stack to access a supplied production hostname or real client data.
- Add networking, security groups, subnets, routing/load balancing, logs, and
  health checks explicitly when making the service reachable.

## Known gaps (current state)

- The ECS service uses `awsvpc` mode without `network_configuration`; it also has
  no load balancer, service discovery, or documented local forwarding path.
- The database password and full `DATABASE_URL` are embedded in configuration
  and task-definition environment variables; the LLM key is also passed as a
  task-definition environment variable rather than through a secrets service.
- The task execution role has no attached policy, and no task role is defined.
- There are no CloudWatch logs, health checks, autoscaling, image digest/version
  pinning, backup policy, deletion protection, or environment separation.
- The API task runs both the API and FastMCP processes and maps ports `4000`
  and `8001`; there is no separate MCP task or public load balancer.
- The RDS resource has no subnet/security group configuration; compatibility
  depends on FakeCloud rather than representing a deployable AWS design.
