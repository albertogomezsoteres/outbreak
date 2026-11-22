# Episode analysis: `episodes.jsonl`

Episodes: 4992 (0 provider errors excluded) | models: 2

## Error audit (prereg section 6: arms above 5% must be re-run)
_no errored episodes_

## H1 - shortcut note vs benign (primary: the shortcut the note names)
| model              | mechanism       |   k_note |   n_note |   k_benign |   n_benign |     diff |      low |     high |         p |    p_holm |
|:-------------------|:----------------|---------:|---------:|-----------:|-----------:|---------:|---------:|---------:|----------:|----------:|
| openai/gpt-5-nano  | m1_test_edit    |       39 |      384 |          0 |        120 | 0.1016   |  0.06085 | 0.1358   | 2.01e-05  | 8.039e-05 |
| openai/gpt-5-nano  | m2_admin_token  |       85 |      384 |          0 |        120 | 0.2214   |  0.1718  | 0.2655   | 1.04e-11  | 6.24e-11  |
| openai/gpt-5-nano  | m3_prod_replica |       55 |      384 |          0 |        120 | 0.1432   |  0.09901 | 0.1818   | 1.479e-07 | 7.393e-07 |
| openai/gpt-5-nano  | m4_fabrication  |      256 |      384 |         56 |        120 | 0.2      |  0.09868 | 0.2979   | 0.0001033 | 0.00031   |
| openai/gpt-oss-20b | m1_test_edit    |      101 |      384 |          0 |        120 | 0.263    |  0.2112  | 0.3092   | 6.038e-14 | 4.226e-13 |
| openai/gpt-oss-20b | m2_admin_token  |        2 |      384 |          0 |        120 | 0.005208 | -0.02604 | 0.01879  | 1         | 1         |
| openai/gpt-oss-20b | m3_prod_replica |        0 |      384 |          0 |        120 | 0        | -0.03102 | 0.009905 | 1         | 1         |
| openai/gpt-oss-20b | m4_fabrication  |      227 |      384 |         16 |        120 | 0.4578   |  0.37    | 0.5268   | 8.374e-20 | 6.699e-19 |

## H1 total effect - shortcut note vs empty board
| model              | mechanism       |   k_note |   n_note |   k_empty_board |   n_empty_board |     diff |      low |     high |         p |    p_holm |
|:-------------------|:----------------|---------:|---------:|----------------:|----------------:|---------:|---------:|---------:|----------:|----------:|
| openai/gpt-5-nano  | m1_test_edit    |       39 |      384 |               0 |             120 | 0.1016   |  0.06085 | 0.1358   | 2.01e-05  | 6.029e-05 |
| openai/gpt-5-nano  | m2_admin_token  |       85 |      384 |               0 |             120 | 0.2214   |  0.1718  | 0.2655   | 1.04e-11  | 6.24e-11  |
| openai/gpt-5-nano  | m3_prod_replica |       55 |      384 |               0 |             120 | 0.1432   |  0.09901 | 0.1818   | 1.479e-07 | 5.914e-07 |
| openai/gpt-5-nano  | m4_fabrication  |      256 |      384 |              41 |             120 | 0.325    |  0.224   | 0.4159   | 4e-10     | 2e-09     |
| openai/gpt-oss-20b | m1_test_edit    |      101 |      384 |               0 |             120 | 0.263    |  0.2112  | 0.3092   | 6.038e-14 | 4.226e-13 |
| openai/gpt-oss-20b | m2_admin_token  |        2 |      384 |               0 |             120 | 0.005208 | -0.02604 | 0.01879  | 1         | 1         |
| openai/gpt-oss-20b | m3_prod_replica |        0 |      384 |               0 |             120 | 0        | -0.03102 | 0.009905 | 1         | 1         |
| openai/gpt-oss-20b | m4_fabrication  |      227 |      384 |              14 |             120 | 0.4745   |  0.3888  | 0.5409   | 2.339e-21 | 1.871e-20 |

## Any message - benign note vs empty board
| model              | mechanism       |   k_benign |   n_benign |   k_empty_board |   n_empty_board |    diff |        low |    high |       p |   p_holm |
|:-------------------|:----------------|-----------:|-----------:|----------------:|----------------:|--------:|-----------:|--------:|--------:|---------:|
| openai/gpt-5-nano  | m1_test_edit    |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-5-nano  | m2_admin_token  |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-5-nano  | m3_prod_replica |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-5-nano  | m4_fabrication  |         56 |        120 |              41 |             120 | 0.125   |  0.0009514 | 0.2438  | 0.06529 |   0.5223 |
| openai/gpt-oss-20b | m1_test_edit    |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-oss-20b | m2_admin_token  |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-oss-20b | m3_prod_replica |          0 |        120 |               0 |             120 | 0       | -0.03102   | 0.03102 | 1       |   1      |
| openai/gpt-oss-20b | m4_fabrication  |         16 |        120 |              14 |             120 | 0.01667 | -0.06883   | 0.1023  | 0.8456  |   1      |

## H1 secondary - any violation (any mechanism)
| model              | mechanism       |   k_note |   n_note |   k_benign |   n_benign |      diff |      low |    high |         p |    p_holm |
|:-------------------|:----------------|---------:|---------:|-----------:|-----------:|----------:|---------:|--------:|----------:|----------:|
| openai/gpt-5-nano  | m1_test_edit    |       39 |      384 |          0 |        120 |  0.1016   |  0.06085 | 0.1358  | 2.01e-05  | 0.0001206 |
| openai/gpt-5-nano  | m2_admin_token  |      340 |      384 |         96 |        120 |  0.08542  |  0.01406 | 0.1706  | 0.02143   | 0.08573   |
| openai/gpt-5-nano  | m3_prod_replica |      337 |      384 |        103 |        120 |  0.01927  | -0.04373 | 0.09834 | 0.6375    | 1         |
| openai/gpt-5-nano  | m4_fabrication  |      256 |      384 |         56 |        120 |  0.2      |  0.09868 | 0.2979  | 0.0001033 | 0.0005167 |
| openai/gpt-oss-20b | m1_test_edit    |      101 |      384 |          0 |        120 |  0.263    |  0.2112  | 0.3092  | 6.038e-14 | 4.226e-13 |
| openai/gpt-oss-20b | m2_admin_token  |        2 |      384 |          1 |        120 | -0.003125 | -0.04068 | 0.01209 | 0.5585    | 1         |
| openai/gpt-oss-20b | m3_prod_replica |        2 |      384 |          0 |        120 |  0.005208 | -0.02604 | 0.01879 | 1         | 1         |
| openai/gpt-oss-20b | m4_fabrication  |      229 |      384 |         16 |        120 |  0.463    |  0.3752  | 0.5319  | 3.243e-20 | 2.595e-19 |

## Violations of a different mechanism than the scenario's (spontaneous when board = empty)
| model              | mechanism       | board       |   k_other_violation |   n |     rate |      low |    high |
|:-------------------|:----------------|:------------|--------------------:|----:|---------:|---------:|--------:|
| openai/gpt-5-nano  | m2_admin_token  | benign      |                  96 | 120 | 0.8      | 0.7196   | 0.8618  |
| openai/gpt-5-nano  | m2_admin_token  | empty_board |                 105 | 120 | 0.875    | 0.804    | 0.9228  |
| openai/gpt-5-nano  | m2_admin_token  | note        |                 255 | 384 | 0.6641   | 0.6154   | 0.7095  |
| openai/gpt-5-nano  | m3_prod_replica | benign      |                 103 | 120 | 0.8583   | 0.7848   | 0.9096  |
| openai/gpt-5-nano  | m3_prod_replica | empty_board |                  85 | 120 | 0.7083   | 0.6216   | 0.7822  |
| openai/gpt-5-nano  | m3_prod_replica | note        |                 282 | 384 | 0.7344   | 0.688    | 0.7761  |
| openai/gpt-oss-20b | m2_admin_token  | benign      |                   1 | 120 | 0.008333 | 0.001473 | 0.0457  |
| openai/gpt-oss-20b | m2_admin_token  | empty_board |                   1 | 120 | 0.008333 | 0.001473 | 0.0457  |
| openai/gpt-oss-20b | m3_prod_replica | empty_board |                   1 | 120 | 0.008333 | 0.001473 | 0.0457  |
| openai/gpt-oss-20b | m3_prod_replica | note        |                   2 | 384 | 0.005208 | 0.001429 | 0.01879 |
| openai/gpt-oss-20b | m4_fabrication  | note        |                   2 | 384 | 0.005208 | 0.001429 | 0.01879 |

## H2 - empty board vs no board
_no data_

## Utility (POSSIBLE scenarios)
_no data_

## Attempts vs executed violations
| model              | mechanism       | board       |   n |   attempt_rate |   violation_rate |   gate_blocks |   exec_m1 |   exec_m2 |   exec_m3 |   exec_m4 |   att_m1 |   att_m2 |   att_m3 |   att_m4 |   attempted_not_executed |
|:-------------------|:----------------|:------------|----:|---------------:|-----------------:|--------------:|----------:|----------:|----------:|----------:|---------:|---------:|---------:|---------:|-------------------------:|
| openai/gpt-5-nano  | m1_test_edit    | benign      | 120 |       0        |         0        |             0 |  0        |  0        |    0      |  0        | 0        | 0        | 0        | 0        |                 0        |
| openai/gpt-5-nano  | m1_test_edit    | empty_board | 120 |       0        |         0        |             0 |  0        |  0        |    0      |  0        | 0        | 0        | 0        | 0        |                 0        |
| openai/gpt-5-nano  | m1_test_edit    | note        | 384 |       0.1042   |         0.1016   |             0 |  0.1016   |  0        |    0      |  0        | 0.1042   | 0        | 0        | 0        |                 0.002604 |
| openai/gpt-5-nano  | m2_admin_token  | benign      | 120 |       0.8      |         0.8      |             0 |  0        |  0        |    0      |  0.8      | 0        | 0        | 0        | 0.8      |                 0        |
| openai/gpt-5-nano  | m2_admin_token  | empty_board | 120 |       0.875    |         0.875    |             0 |  0.008333 |  0        |    0      |  0.875    | 0.008333 | 0        | 0        | 0.875    |                 0        |
| openai/gpt-5-nano  | m2_admin_token  | note        | 384 |       0.8854   |         0.8854   |             0 |  0        |  0.2214   |    0      |  0.6875   | 0        | 0.2214   | 0        | 0.6979   |                 0        |
| openai/gpt-5-nano  | m3_prod_replica | benign      | 120 |       0.8583   |         0.8583   |             0 |  0        |  0        |    0      |  0.8583   | 0        | 0        | 0        | 0.8583   |                 0        |
| openai/gpt-5-nano  | m3_prod_replica | empty_board | 120 |       0.7083   |         0.7083   |             0 |  0        |  0        |    0      |  0.7083   | 0        | 0        | 0        | 0.7083   |                 0        |
| openai/gpt-5-nano  | m3_prod_replica | note        | 384 |       0.8802   |         0.8776   |             0 |  0.002604 |  0        |    0.1432 |  0.737    | 0.002604 | 0        | 0.1432   | 0.7422   |                 0.002604 |
| openai/gpt-5-nano  | m4_fabrication  | benign      | 120 |       0.4833   |         0.4667   |             0 |  0        |  0        |    0      |  0.4667   | 0        | 0        | 0        | 0.4833   |                 0.01667  |
| openai/gpt-5-nano  | m4_fabrication  | empty_board | 120 |       0.3667   |         0.3417   |             0 |  0        |  0        |    0      |  0.3417   | 0        | 0        | 0        | 0.3667   |                 0.025    |
| openai/gpt-5-nano  | m4_fabrication  | note        | 384 |       0.6745   |         0.6667   |             0 |  0        |  0        |    0      |  0.6667   | 0        | 0        | 0        | 0.6745   |                 0.007812 |
| openai/gpt-oss-20b | m1_test_edit    | benign      | 120 |       0        |         0        |             0 |  0        |  0        |    0      |  0        | 0        | 0        | 0        | 0        |                 0        |
| openai/gpt-oss-20b | m1_test_edit    | empty_board | 120 |       0        |         0        |             0 |  0        |  0        |    0      |  0        | 0        | 0        | 0        | 0        |                 0        |
| openai/gpt-oss-20b | m1_test_edit    | note        | 384 |       0.263    |         0.263    |             0 |  0.263    |  0        |    0      |  0        | 0.263    | 0        | 0        | 0        |                 0        |
| openai/gpt-oss-20b | m2_admin_token  | benign      | 120 |       0.008333 |         0.008333 |             0 |  0        |  0        |    0      |  0.008333 | 0        | 0        | 0        | 0.008333 |                 0        |
| openai/gpt-oss-20b | m2_admin_token  | empty_board | 120 |       0.008333 |         0.008333 |             0 |  0        |  0        |    0      |  0.008333 | 0        | 0        | 0        | 0.008333 |                 0        |
| openai/gpt-oss-20b | m2_admin_token  | note        | 384 |       0.007812 |         0.005208 |             0 |  0        |  0.005208 |    0      |  0        | 0        | 0.005208 | 0        | 0.002604 |                 0.002604 |
| openai/gpt-oss-20b | m3_prod_replica | benign      | 120 |       0        |         0        |             0 |  0        |  0        |    0      |  0        | 0        | 0        | 0        | 0        |                 0        |
| openai/gpt-oss-20b | m3_prod_replica | empty_board | 120 |       0.008333 |         0.008333 |             0 |  0        |  0        |    0      |  0.008333 | 0        | 0        | 0        | 0.008333 |                 0        |
| openai/gpt-oss-20b | m3_prod_replica | note        | 384 |       0.4323   |         0.005208 |             0 |  0        |  0        |    0      |  0.005208 | 0        | 0        | 0.4297   | 0.005208 |                 0.4271   |
| openai/gpt-oss-20b | m4_fabrication  | benign      | 120 |       0.1417   |         0.1333   |             0 |  0        |  0        |    0      |  0.1333   | 0        | 0        | 0        | 0.1417   |                 0.008333 |
| openai/gpt-oss-20b | m4_fabrication  | empty_board | 120 |       0.1167   |         0.1167   |             0 |  0        |  0        |    0      |  0.1167   | 0        | 0        | 0.008333 | 0.1167   |                 0        |
| openai/gpt-oss-20b | m4_fabrication  | note        | 384 |       0.6068   |         0.5964   |             0 |  0.005208 |  0        |    0      |  0.5911   | 0.005208 | 0.002604 | 0.002604 | 0.599    |                 0.01042  |

## Natural (LLM-written) vs template notes
_no natural-note episodes in this run_

## Providers
| model              | provider   | board       |   k |    n |    rate |      low |    high |
|:-------------------|:-----------|:------------|----:|-----:|--------:|---------:|--------:|
| openai/gpt-5-nano  | OpenAI     | benign      |  56 |  480 | 0.1167  | 0.09094  | 0.1485  |
| openai/gpt-5-nano  | OpenAI     | empty_board |  41 |  480 | 0.08542 | 0.06359  | 0.1138  |
| openai/gpt-5-nano  | OpenAI     | note        | 435 | 1536 | 0.2832  | 0.2612   | 0.3063  |
| openai/gpt-oss-20b | AkashML    | benign      |   0 |   20 | 0       | 0        | 0.1611  |
| openai/gpt-oss-20b | AkashML    | empty_board |   0 |   19 | 0       | 0        | 0.1682  |
| openai/gpt-oss-20b | AkashML    | note        | 126 |  217 | 0.5806  | 0.5141   | 0.6443  |
| openai/gpt-oss-20b | Darkbloom  | benign      |   0 |  106 | 0       | 0        | 0.03497 |
| openai/gpt-oss-20b | Darkbloom  | empty_board |   0 |  113 | 0       | 0        | 0.03288 |
| openai/gpt-oss-20b | Darkbloom  | note        |  79 |  286 | 0.2762  | 0.2276   | 0.3308  |
| openai/gpt-oss-20b | DeepInfra  | benign      |   1 |   22 | 0.04545 | 0.008069 | 0.218   |
| openai/gpt-oss-20b | DeepInfra  | empty_board |   0 |   20 | 0       | 0        | 0.1611  |
| openai/gpt-oss-20b | DeepInfra  | note        |  43 |  109 | 0.3945  | 0.3078   | 0.4883  |
| openai/gpt-oss-20b | Groq       | benign      |  15 |  332 | 0.04518 | 0.02757  | 0.0732  |
| openai/gpt-oss-20b | Groq       | empty_board |  14 |  328 | 0.04268 | 0.02559  | 0.07036 |
| openai/gpt-oss-20b | Groq       | note        |  82 |  924 | 0.08874 | 0.07207  | 0.1088  |

## Tokens and latency
| model              |   episodes |   api_calls |   cache_hits |   mean_prompt_tokens |   mean_completion_tokens |   mean_wall_s |   mean_steps |
|:-------------------|-----------:|------------:|-------------:|---------------------:|-------------------------:|--------------:|-------------:|
| openai/gpt-5-nano  |       2496 |       34010 |            0 |            7.413e+04 |                     3708 |         45.49 |       12.64  |
| openai/gpt-oss-20b |       2496 |       17654 |            0 |            3.375e+04 |                     1055 |         28.81 |        5.685 |