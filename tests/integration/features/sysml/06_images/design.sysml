package 'Image design' {
    part def Display {
        doc /*
         * Display layout:
         *
         * .. image:: ./_assets/diagram.svg
         */
        satisfy 'IMG-REQ-1' by display;
        part display : Display;
    }
}
