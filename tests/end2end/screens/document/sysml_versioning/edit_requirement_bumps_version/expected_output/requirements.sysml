package 'Requirements' {
    requirement <'REQ-1'> 'Parent' {
        @StrictDocVersioning::ItemVersion { version = 2; contentHash = "bb0d224716237fc6"; }
        doc /*
         * Changed parent statement.
         */
    }

    requirement <'REQ-2'> 'Child' {
        @StrictDocVersioning::ItemVersion { version = 1; contentHash = "828af0825f50d79c"; }
        doc /*
         * Child statement.
         */
    }

    dependency from 'REQ-2' to 'REQ-1' {
        @StrictDocVersioning::TracedVersion { version = 2; }
    }
}
