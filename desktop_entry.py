import sys

if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--transcribe-worker':
        from any2any.transcribe_worker import main
        main(sys.argv[2:]); raise SystemExit(0)
    if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
        from any2any.selftest import run
        raise SystemExit(0 if run(sys.argv[2]) else 1)
    from any2any.gui import main
    main()
