=======
History
=======

0.2.0 (2025-06-23)
-------------------

* Allow overriding the entire cap_app_name of a one-click app (#14)
* BREAKING: Drop namespace parameter for one-click app (#14)
* Auto-assign tag when deploying one-click app (#14)
* Override one-click app tag on deploy_one_click_app & update_app (#20)
* Add projects support (#18)

0.1.24 (2024-12-16)
-------------------

* Support "command" in service_update_override for one-click apps (#13)
* Fix & test update from novel kwargs (#12)
* update method lets you set httpAuth (#11)
* `update()` now handles persistent directories that use hostPath (#7)
* `gen_random_hex` works across whole one-click-app YAML (#6)
* Bugfix: `update()` should not change notExposeAsWebApp (#8)
* Enable SSL on base domain (#9)
* Allow optional override one-click repository path (#5)

0.1.0 (2021-06-11)
------------------

* First release on PyPI.
