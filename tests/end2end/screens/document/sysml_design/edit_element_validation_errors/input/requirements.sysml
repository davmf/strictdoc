package 'Requirements' {
    requirement <'SYS-THR-001'> 'Shift throughput' {
        doc /*
         * The instrument shall complete at least 96 samples.
         */
        attribute requiredSamplesPerShift : Real = 96;
    }
}
