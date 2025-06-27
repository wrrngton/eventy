# Events

Send synthetic events to an Algolia index for the purposes of demonstrating features such as analytics, drr, personalisation etc.

It uses a weighted distribution to prevent skewed simulations.

## Configuration

A configuration is a set of instructions and data used to run searches and events on a specific Algolia index. 

Each configuration should be stored in it's own directory within the `configs/` directory.

Each directory should contain four files:

- `config.toml`
- `filters.json`
- `profiles.json`
- `searches.json`

The structure of these files is available in the `config-sample/` directory.

## Running remotely

The idea is that you can run this script on a remote machine multiple times to have constant index training.

To do this you'll need to run a cronjob that pings the app and pass the directory of Algolia configuration with the flag `--config-dir`, for example:

```console
python3 script.py --config-dir "manufacturing"
```
