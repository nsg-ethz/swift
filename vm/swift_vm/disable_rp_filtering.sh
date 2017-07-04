for i in /proc/sys/net/ipv4/conf/*/rp_filter ; do
    echo 0 > $i
done
