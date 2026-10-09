#include "unity.h"

void run_basics_tests(void);
void run_lifecycle_tests(void);
void run_sensing_tests(void);
void run_command_tests(void);
void run_config_tests(void);
void run_fuzz_tests(void);
void run_hal_logic_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UNITY_BEGIN();
    run_basics_tests();
    run_lifecycle_tests();
    run_sensing_tests();
    run_command_tests();
    run_config_tests();
    run_fuzz_tests();
    run_hal_logic_tests();
    return UNITY_END();
}
